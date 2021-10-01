# coding=utf-8
import os
import sys
import threading
import time
import traceback
from tkinter import Tk, messagebox, Label, Entry, StringVar, Button, filedialog

from message_stdout import Messagebox
from rpk_converter import RpkConverter
from util import resource_path


class App:
    def __init__(self, title):
        self.title = title
        self.root = Tk()
        self.root.title(title)
        self.rpk_file_path = StringVar()
        self.out_dir = StringVar()
        self.status = ""
        # layout
        Label(self.root, text="选择从记乎导出的rpk文件").grid(row=0, column=0)
        Entry(self.root, textvariable=self.rpk_file_path, width=100).grid(row=0, column=1)
        Button(self.root, text="选择", command=self.select_rpk_file_path).grid(row=0, column=2)
        Label(self.root, text="选择输出apkg的文件夹").grid(row=1, column=0)
        Entry(self.root, textvariable=self.out_dir, width=100).grid(row=1, column=1)
        Button(self.root, text="选择", command=self.select_out_dir).grid(row=1, column=2)
        self.run_button = Button(self.root, text="开始转换", width=100, command=self.touch_button)
        self.run_button.grid(row=2, column=0, columnspan=3)
        self.root.grid_rowconfigure(0, minsize=50)
        self.root.grid_rowconfigure(1, minsize=50)
        self.root.grid_rowconfigure(2, minsize=70)
        # window resize
        screenwidth = self.root.winfo_screenwidth()
        screenheight = self.root.winfo_screenheight()
        self.root.geometry('+%d+%d' % ((screenwidth - 1000) / 2, (screenheight - 300) / 2))
        self.root.resizable(width=True, height=True)
        # mainloop
        messagebox.showinfo(title, "这个工具用于将rpk文件转换为Anki的apkg文件，用于在anki中学习")
        self.root.mainloop()

    def select_rpk_file_path(self):
        input_path = filedialog.askopenfilename()
        if not input_path:
            return
        if not input_path.endswith(".rpk"):
            messagebox.showerror(title, f"选择中的文件并不是rpk文件，请重新选择：{os.path.basename(input_path)}")
            return
        self.rpk_file_path.set(input_path)
        if self.out_dir.get().__len__() == 0 and len(input_path) > 0:
            self.out_dir.set(os.path.dirname(input_path))

    def select_out_dir(self):
        self.out_dir.set(filedialog.askdirectory())

    def touch_button(self):
        self.run_button.config(state="disabled")
        thread_convert = threading.Thread(target=self.run_convert)
        thread_convert.start()
        thread_count = threading.Thread(target=self.time_count)
        thread_count.start()

    def run_convert(self):
        rpk_file_path = self.rpk_file_path.get().replace("\\", "/")
        out_dir = self.out_dir.get().replace("\\", "/")
        sqlite_path = resource_path("static/template.sqlite3")
        if not out_dir:
            out_dir = os.getcwd().replace("\\", "/")

        message_stdout.clear()
        converter = RpkConverter(rpk_file_path, out_dir, sqlite_path)
        try:
            self.status = "正在解析RPK文件(解压缩)"
            converter.read_rpk()
            self.status = "正在解析RPK文件(分析json)"
            converter.load_rpk_json()
            self.status = "正在生成apkg文件(写入sqlite)"
            converter.write_to_sqlite()
            def on_progress(idx, count):
                self.status = f'正在下载音频、图片文件({idx}/{count})'
            converter.download_resource_files(on_progress)
            self.status = "正在生成apkg文件(转换media文件)"
            converter.convert_media_files()
            self.status = "正在生成apkg文件(打包为apkg)"
            converter.pack_apkg()
            messagebox.showinfo(self.title, "转换成功！请打开 " + out_dir + " 查看生成的apkg文件")
        except Exception as e:
            messagebox.showerror(title, "**ERROR**\n" + str(
                e) + "\n\n To check the complete traceback error log, please open the console.")
            sys.stderr.write(traceback.format_exc())
        finally:
            self.status = "清除临时文件"
            # converter.clear_tmp_files()
            # message_stdout.send_message()
            self.run_button.config(text="run", state="normal")

    def time_count(self):
        count = 0
        while self.run_button['state'] == "disabled" and count < 1000:
            self.run_button['text'] = f"{count}s...{self.status}"
            count += 1
            time.sleep(1)


title = "RpkConverter"
message_stdout = Messagebox(title)
app = App(title=title)
