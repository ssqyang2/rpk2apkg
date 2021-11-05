import os
import re
import sys


def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def is_capital_letter(char):
    return len(char) == 1 and char.isupper()


def convert_to_apkg_format(f):
    if not f:
        return ""
    f = str(f)
    f = f.replace(r"[audio:aws_", "[sound:")
    f = f.replace(r"[audio:", "[sound:")
    f = re.sub(r"\[image:(.*?)\]", r'<img src="\1">', f)
    f = re.sub(r"__([^_,]{1,100}?)__", r"{{c1::\1}}", f)
    # remove spaces in cloze
    f = re.sub(r"{{c1::\s*(.*?)\s*}}", r"{{c1::\1}}", f)
    f = re.sub(r"\[hide:(.*?)\]", r"{{c1::\1}}", f)
    return f.strip()
