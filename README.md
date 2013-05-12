用 LaTeX 排版技术书籍
=====================
##PDF下载
<http://code.google.com/p/chenshuo/downloads/detail?name=typeset.pdf>

##在Windows下编译
1. 安装Tex Live 2012 <http://www.tug.org/texlive/>。把bin目录例如`D:\texlive\2012\bin\win32`加入PATH环境变量。
2. 安装TeXstudio <http://texstudio.sourceforge.net/>
3. (可选)启动Tex Live Manager，更新所有已安装的软件包。
4. 安装字体。在Windows下，这个LaTex模板额外使用了5个字体，下载地址 <http://weibo.com/1663402687/zrSNhgTGK>
5. 配置TeXstudio。

    启动Texstudio，选择 `Options-->Configure Texstudio-->Commands`，XeLaTex 设置为 `xelatex -synctex=1 -interaction=nonstopmode %.tex`；

    选择 `Options-->Configure Texstudio-->Build`

    Build & View 由默认的 PDF Chain 改为 Compile & View；

    Default Compiler 由默认的PdfLaTex 修改为 XeLaTex ；

    PDF Viewer 改为 “Internal PDF Viewer(windowed)”，这样预览时会弹出一个独立的窗口，这样比较方便。

6. 编译。用TeXstudio打开`typeset.tex`，点击界面上的绿色箭头就可以开始编译了。

    在下方的窗口可以看到TeXstudio正在使用的编译命令是`xelatex -synctex=1 -interaction=nonstopmode "typeset".tex`
