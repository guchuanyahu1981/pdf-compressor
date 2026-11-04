# PDF 压缩工具

带图形界面的 PDF 压缩程序,基于 Python、tkinter 和 PyMuPDF。

## 功能

- 批量添加 PDF 文件,列表显示原大小、压缩后大小、节省比例和状态
- 三档压缩级别:轻度、中度、强度(降低图片分辨率并重新编码为 JPEG,同时清理冗余对象)
- 可选择输出目录,默认保存在源文件旁,文件名加 `_compressed` 后缀,不会覆盖原文件
- 若压缩后反而变大,则保留原文件内容
- 后台线程压缩,界面不卡顿;加密或损坏的文件会提示失败并继续处理其他文件

## 安装

```
pip install -r requirements.txt
```

需要 Python 3.8 及以上(自带 tkinter)。

## 运行

```
python main.py
```

## 使用方法

1. 点击“添加文件”选择一个或多个 PDF
2. 选择压缩级别和输出目录(可不选)
3. 点击“开始压缩”,等待进度条完成

## 测试

```
pytest tests/
```

## 打包为可执行文件

```
pip install pyinstaller
pyinstaller -F -w main.py -n PDF压缩工具
```
