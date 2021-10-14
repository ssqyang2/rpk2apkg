import json
import sqlite3
from collections import OrderedDict
from copy import deepcopy

from anki_base import *
from misc import *
from util import *

# logger = get_logger("AnkiCollectionWriter")


class AnkiCollectionWriter:
    def __init__(self,
                 root_deck_name: str,
                 collection_path: str,
                 cats_df: OrderedDict,
                 cards_df: OrderedDict,
                 tpls_df: OrderedDict
                 ):
        assert os.path.exists(collection_path), f"File not exists: {collection_path}"
        self.con = sqlite3.connect(collection_path)
        self.root_deck_name = root_deck_name
        self.cats_df = cats_df
        self.cards_df = cards_df
        self.tpls_df = tpls_df

    def close(self):
        self.con.close()

    def clear_old_rows(self):
        with self.con as c:
            c.execute("DELETE FROM cards")
            c.execute("DELETE FROM notes")
            c.execute("DELETE FROM revlog")
            c.execute("DELETE FROM col")
            c.commit()

    def load_replace_model(self, type):
        model_path = ""
        if type == "select":
            model_path = "static/anki-awesome-select.json"

        f = open(resource_path(model_path), "r", encoding="utf-8")
        return json.load(f)

    def get_decks(self):
        def get_deck_name(idx, child_name=None):
            """recursively build the deck name"""
            row = self.cats_df[idx]
            deck_name = row['name'] if child_name is None else f"{row['name']}::{child_name}"
            if row['pid'] == 0:
                return self.root_deck_name + "::" + deck_name
            else:
                return get_deck_name(row['pid'], deck_name)

        decks = {}
        for idx, row in self.cats_df.items():
            deck_info = deepcopy(BASE_DECK)
            deck_info['id'] = idx
            deck_info['name'] = get_deck_name(idx)
            deck_info['name'] = get_deck_name(idx)
            decks[str(idx)] = deck_info
        return decks

    @staticmethod
    def process_tmpl(tmpl: str):
        return str(tmpl).replace("{{@", "{{")

    def get_models(self):
        models = {}
        for idx, row in self.tpls_df.items():
            if "选择" in row['name']:
                model = self.load_replace_model("select")
            else:
                model = deepcopy(BASE_MODEL)
                model['name'] = row['name']
                model['css'] += row['css']
                for ord, f in enumerate(row['fields']):
                    field = deepcopy(BASE_FIELD)
                    field['name'] = f['name']
                    field['ord'] = ord
                    model['flds'].append(field)
                tmpl = deepcopy(BASE_TMPL)
                if "填空" in row['name']:
                    tmpl['qfmt'] = self.process_tmpl(row['front']).replace("{{问题}}", "{{cloze:问题}}")
                    tmpl['afmt'] = self.process_tmpl(row['back']).replace("{{问题}}", "{{cloze:问题}}")
                else:
                    tmpl['qfmt'] = self.process_tmpl(row['front'])
                    tmpl['afmt'] = self.process_tmpl(row['back'])
                model['tmpls'].append(tmpl)

                # handle double-sided cards
                if len(row['front_back'].strip()) > 0:
                    model2 = deepcopy(BASE_MODEL)
                    model2['name'] = row['name'] + "_back"
                    model2['css'] += row['css_back']
                    # XXX: use N+1 as back's model id
                    model2['id'] = str(idx + 1)
                    for ord, f in enumerate(row['fields']):
                        field = deepcopy(BASE_FIELD)
                        field['name'] = f['name']
                        field['ord'] = ord
                        model2['flds'].append(field)
                    tmpl = deepcopy(BASE_TMPL)
                    tmpl['qfmt'] = self.process_tmpl(row['front_back'])
                    tmpl['afmt'] = self.process_tmpl(row['back_back'])
                    model2['tmpls'].append(tmpl)
                    models[str(idx + 1)] = model2

            model['id'] = str(idx)
            models[str(idx)] = model
        return models

    def insert_col_table(self):
        models = self.get_models()
        decks = self.get_decks()
        conf = deepcopy(BASE_CONF)
        deck_id = int(next(iter(decks)))
        conf['activeDecks'] = [deck_id]
        conf['curDeck'] = deck_id
        conf['curModel'] = next(iter(models))

        with self.con as c:
            c.execute('INSERT INTO col (id, crt, mod, scm, ver, dty, usn, ls, conf, models, decks, dconf, tags)'
                      ' values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (1, now_sec(), now_ms(), now_ms(), SCHEMA_VERSION, 0, 0, 0,
                       # conf
                       json.dumps(conf),
                       json.dumps(models),
                       json.dumps(decks),
                       json.dumps(BASE_DCONF),
                       json.dumps(BASE_TAGS)
                       ))

            c.commit()

    def insert_fields_to_notes(self, idx, fields_dict, model):
        fields = []
        # insert fields according to static/anki-awesome-select.json
        if model['name'] == "AwesomeSelect-3.x":
            fields = [
                str(idx), # id
                convert_to_apkg_format(fields_dict.get("question")) # question
            ]
            # options
            options = []
            for field_name in fields_dict.keys():
                f = convert_to_apkg_format(fields_dict.get(field_name))
                if is_capital_letter(field_name):
                    options.append(f)
            fields.append("||".join(filter(lambda x: len(x) > 0, options)))

            # answer
            # convert to 1, 2, 3
            answer_list = [str(ord(x) - ord("A") + 1) for x in fields_dict.get("answer")]
            fields.append("||".join(answer_list))

            # notes
            fields.append(convert_to_apkg_format(fields_dict.get("explain")))
        else:
            # insert fields by default
            for field_name in [x['name'] for x in model['flds']]:
                f = convert_to_apkg_format(fields_dict.get(field_name))
                fields.append(f)
        return fields

    def insert_notes_table(self):
        models = self.get_models()

        cnt = 0
        with self.con as c:
            for idx, row in self.cards_df.items():
                # 跳过“未分类”卡片
                if row['aid'] == 0:
                    continue
                # assert row['aid'] != 0, f"Invalid deck for card: {row['data']}"
                # logger.info(f'Writing card {row}')
                cnt += 1
                tid = row['tid']
                model_id = tid
                if row['is_back'] == 1:
                    model_id += 1
                model = models[str(model_id)]
                fields_dict = row['data']
                fields = self.insert_fields_to_notes(idx, fields_dict, model)

                c.execute("INSERT INTO notes (id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)"
                          " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (idx, gen_guid(), model_id, now_sec(), -1, '',
                           # flds
                           '\x1f'.join(fields),
                           fields[0],
                           # fake csum
                           random.randint(0, 1000000),
                           0, ''
                           ))
                c.execute(
                    "INSERT INTO cards (id, nid, did, ord, mod, usn, type, queue, due, ivl, factor, reps, lapses, left, odue, odid, flags, data)"
                    " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (idx, idx,  # same cid, did
                     row['aid'],  # aid (cats id) as did
                     0,  # ord
                     now_sec(),
                     -1, 0, 0,
                     cnt,  # from 1 as due
                     0, 0, 0, 0, 0, 0, 0, 0,
                     ''
                     ))
            c.commit()
