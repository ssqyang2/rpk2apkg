import json
import logging
import os
import shutil
import time
import zipfile
from collections import OrderedDict
import requests
from multiprocessing.pool import ThreadPool
from util import resource_path

from anki_collection_writer import AnkiCollectionWriter

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

DOWNLOAD_THREADS = 20
web_client = requests.Session()
retry = Retry(total=3)
adapter = HTTPAdapter(pool_connections=DOWNLOAD_THREADS, pool_maxsize=DOWNLOAD_THREADS, max_retries=retry)
web_client.mount('http://', adapter)
web_client.mount('https://', adapter)



class RpkConverter:
    def __init__(self,
                 file_path: str,
                 out_dir: str,
                 sqlite_path: str
                 ):
        self.rpk_file_path = file_path
        self.sqlite_path = sqlite_path
        self.filename = os.path.splitext(os.path.split(self.rpk_file_path)[1])[0]

        self.out_dir = out_dir
        # temp files directory labeled for concurrent
        local_time = time.strftime("%y%m%d%H%M%S", time.localtime())
        self.tmp_dir = f"{out_dir}/temp{local_time}"
        self.rpk_tmp_dir = f"{self.tmp_dir}/rpk"
        self.apkg_tmp_dir = f"{self.tmp_dir}/apkg"
        os.mkdir(self.tmp_dir)
        os.mkdir(self.rpk_tmp_dir)
        os.mkdir(self.apkg_tmp_dir)

        self.media_files_path = f"{self.rpk_tmp_dir}/resources"

        self.cards_df = None
        self.carts_df = None
        self.tpls_df = None

    def read_rpk(self):
        assert os.path.exists(self.rpk_file_path), f"File not exists: {self.rpk_file_path}"
        assert zipfile.is_zipfile(self.rpk_file_path), f"Not valid rpk file: {self.rpk_file_path}"
        logging.info("Reading from rpk file")
        zipf = zipfile.ZipFile(self.rpk_file_path, "r", zipfile.ZIP_DEFLATED)
        zipf.extractall(self.rpk_tmp_dir)
        zipf.close()

    def load_rpk_json(self):
        logging.info("Loading rpk json")
        with open(f"{self.rpk_tmp_dir}/data/cards.json", encoding="utf-8") as f:
            obj = json.load(f)

        self.cards_df = OrderedDict({x["cid"]: x for x in obj})

        # df[df['cid'] == df.iloc[0]['related_cid']]

        with open(f"{self.rpk_tmp_dir}/data/cats.json", encoding="utf-8") as f:
            obj = json.load(f)

        self.carts_df = OrderedDict({x["aid"]: x for x in obj})

        with open(f"{self.rpk_tmp_dir}/data/tpls.json", encoding="utf-8") as f:
            obj = json.load(f)
        self.tpls_df = OrderedDict({x["tid"]: x for x in obj})

        resources_file = f"{self.rpk_tmp_dir}/data/resources.json"
        if os.path.exists(resources_file):
            with open(resources_file, encoding="utf-8") as f:
                obj = json.load(f)
            self.resources_df = OrderedDict({x["id"]: x for x in obj})
        else:
            self.resources_df = OrderedDict()

    def write_to_sqlite(self):
        logging.info("Writing to sqlite3")
        cw = AnkiCollectionWriter(self.filename, self.sqlite_path,
                                  cats_df=self.carts_df, cards_df=self.cards_df, tpls_df=self.tpls_df)
        cw.clear_old_rows()

        cw.insert_col_table()
        cw.insert_notes_table()

    def download_resource_files(self, progress_callback):
        ''' progress_callback: (currentCount, totalCount) '''
        os.makedirs(f'{self.rpk_tmp_dir}/resources/', exist_ok=True)
        pool = ThreadPool(DOWNLOAD_THREADS)
        futures = []

        def download_file(name, url):
            with web_client.get(url, stream=True) as r:
                r.raise_for_status()
                with open(f'{self.rpk_tmp_dir}/resources/{name}', 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        # If you have chunk encoded response uncomment if
                        # and set chunk_size parameter to None.
                        # if chunk:
                        f.write(chunk)

        for idx, row in self.resources_df.items():
            name = row['name']
            url = row['url']
            type = row['type']
            if type != 1:
                # type = 1, TTS resources, skip
                f = pool.apply_async(download_file, (name, url))
                futures.append(f)

        for idx, f in enumerate(futures):
            f.get()
            progress_callback(idx, len(futures))

    def convert_media_files(self):
        logging.info("Converting media files")
        media_list = os.listdir(self.media_files_path) if os.path.exists(self.media_files_path) else []
        media_dict = {}
        for i in range(len(media_list)):
            filename = media_list[i]
            os.rename(f"{self.media_files_path}/{filename}", f"{self.media_files_path}/{i}")
            media_dict[f"{i}"] = filename
        for f in ['icon-correct.png', 'icon-correct-2.png', 'icon-correct-not-selected.png', 'icon-error.png', 'icon-error-2.png']:
            i = len(media_dict)
            shutil.copyfile(resource_path(f"static/{f}"), f"{self.media_files_path}/{i}")
            media_dict[f"{i}"] = "_" + f
        json.dump(media_dict, open(f"{self.apkg_tmp_dir}/media", "w"))

    def pack_apkg(self):
        logging.info("Packing into apkg file")
        zipf = zipfile.ZipFile(f"{self.out_dir}/{self.filename}.apkg", 'w', zipfile.ZIP_DEFLATED)
        zipf.write(f"{self.apkg_tmp_dir}/media", "media")
        zipf.write(self.sqlite_path, "collection.anki2")
        media_list = os.listdir(self.media_files_path) if os.path.exists(self.media_files_path) else []
        for media_file in media_list:
            zipf.write(f"{self.media_files_path}/{media_file}", media_file)
        zipf.close()
        done_message = f"转换成功！输出文件在 {self.out_dir}/{self.filename}.apkg \n 你可以选择下一个文件进行转换。"
        logging.info(done_message)
        print(done_message)

    def clear_tmp_files(self):
        logging.info("Deleting temp files")
        error_message = "Delete temp files failed. Please delete them manually."
        try:
            shutil.rmtree(self.tmp_dir)
        except:
            logging.error(error_message)
            print(error_message)
