### RpkConverter

This tool is used to convert rpk file to Anki apkg.

如果遇到任何问题，请发起issue，并描述情况。如果转换rpk出现问题，请将文件发到邮箱 `ssqyang2 [AT] outlook.com`，我会debug并修复问题。

（我是 ssqyang, 用同学电脑注册github，结果账号找不到了。。所以以后维护都在这个repo里进行了~）


# 下载 & 使用
前往 https://github.com/ssqyang2/rpk2apkg/releases　下载已经打包好的程序。

本项目完全开源，如果不放心，可以或者按下面的方法自行打包。

## 如何导出RPK包？
在记乎卡编器里，按截图导出

![jihu export](https://user-images.githubusercontent.com/89735777/131478910-76b2ced4-c328-421b-bc64-786df19805c7.png)



# Build

To pack the .py files into executable file, please execute the following command in the command line:

```shell
# if pyinstaller is not installed
pip install pyinstaller
# -w will hide the console window
# Windows
pyinstaller -w -F main.py --add-data "static/*;./static" --workpath temp --distpath . -n RpkConverter.exe
# Mac
pyinstaller -w -F main.py --add-data "static/*:./static" --workpath temp --distpath . -n RpkConverter
```

The pyinstaller will generate /temp directory to store temp files, which can be deleted manually.

