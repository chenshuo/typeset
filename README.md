# 用 LaTeX 排版技术书籍

## PDF 下载

* [用 LaTeX 排版编程技术书籍的一些个人经验](typeset.pdf)
* [汉字激光照排小史](wangxuan-history.pdf)
    * 复刻 1979 年王选教授研制的华光I型汉字激光照排系统排出的[第一张 8 开报纸样张](wangxuan1979.pdf)
* [TikZ 绘制中学几何题](tikz-notes.ipynb)

***

以下说明由网友 Frank Dai (https://github.com/soulmachine) 编写。

## 如何编译PDF

### 命令行编译

```bash
docker run -it --rm -v $(pwd):/project -w /project soulmachine/texlive xelatex -interaction=nonstopmode typeset.tex
```

### vscode下编译

本项目已经配置好了vscode devcontainer, 可以在 Windows, Linux 和 macOS 三大平台上编译。

用 vscode 打开本项目，选择右下角弹出的 `"Reopen in Container"`，就会在容器中打开本项目，该容器安装了 Tex Live 2022 以及所需要的10个字体。

点击vscode左下角的齿轮图标，选择 `Command Palette`，输入`tasks`, 选择 `Run Task`， 选择 `typeset`，即可启动编译。
