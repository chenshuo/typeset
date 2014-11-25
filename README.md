用 LaTeX 排版技术书籍
=====================
##PDF下载
<http://code.google.com/p/chenshuo/downloads/detail?name=typeset.pdf>

##在Windows下编译
1. 安装Tex Live 2013 <http://www.tug.org/texlive/>。把bin目录例如`D:\texlive\2013\bin\win32`加入PATH环境变量。
1. 安装字体。这个LaTex模板总共使用了9个字体，下载地址 <http://pan.baidu.com/s/1gdefYiJ> ，有的字体Windows自带了，有的字体Ubuntu自带了，但都不全，还是一次性安装完所有字体比较方便。
1. 安装TeXstudio <http://texstudio.sourceforge.net/>
1. (可选)启动Tex Live Manager，更新所有已安装的软件包。
1. 配置TeXstudio。

    启动Texstudio，选择 `Options-->Configure Texstudio-->Commands`，XeLaTex 设置为 `xelatex -synctex=1 -interaction=nonstopmode %.tex`；

    选择 `Options-->Configure Texstudio-->Build`

    Build & View 由默认的 PDF Chain 改为 Compile & View；

    Default Compiler 由默认的PdfLaTex 修改为 XeLaTex ；

    PDF Viewer 改为 “Internal PDF Viewer(windowed)”，这样预览时会弹出一个独立的窗口，这样比较方便。

1. 编译。用TeXstudio打开`typeset.tex`，点击界面上的绿色箭头就可以开始编译了。

    在下方的窗口可以看到TeXstudio正在使用的编译命令是`xelatex -synctex=1 -interaction=nonstopmode "typeset".tex`

##在Ubuntu下编译
1. 安装Tex Live 2013 <http://www.tug.org/texlive/>
	
	1.1. 下载TexLive 2013 的ISO 光盘，地址 <http://www.tug.org/texlive/acquire-iso.html>

    1.2 mount 光盘，`sudo ./install-tl` 开始安装

	1.3 加入环境变量

		sudo vi /etc/profile
		export PATH=$PATH:/usr/local/texlive/2013/bin/x86_64-linux
		export MANPATH=$MANPATH:/usr/local/texlive/2013/texmf-dist/doc/man
		export INFPATH=$INFPATH:/usr/local/texlive/2013/texmf-dist/doc/info

1. 安装字体。这个LaTex模板总共使用了9个字体，下载地址 <http://pan.baidu.com/s/1gdefYiJ> ，有的字体Windows自带了，有的字体Ubuntu自带了，但都不全，还是一次性安装完所有字体比较方便。
1. 安装TeXstudio <http://texstudio.sourceforge.net/>
1. 配置TeXstudio。

    启动Texstudio，选择 `Options-->Configure Texstudio-->Commands`，XeLaTex 设置为 `xelatex -synctex=1 -interaction=nonstopmode %.tex`；

    选择 `Options-->Configure Texstudio-->Build`

    Build & View 由默认的 PDF Chain 改为 Compile & View；

    Default Compiler 由默认的PdfLaTex 修改为 XeLaTex ；

    PDF Viewer 改为 “Internal PDF Viewer(windowed)”，这样预览时会弹出一个独立的窗口，这样比较方便。

1. 编译。用TeXstudio打开`typeset.tex`，点击界面上的绿色箭头就可以开始编译了。

    在下方的窗口可以看到TeXstudio正在使用的编译命令是`xelatex -synctex=1 -interaction=nonstopmode "typeset".tex`
1. 懒人版镜像。如果不想进行上面繁琐的安装过程，我做好了一个Ubuntu VMware虚拟机镜像，已经装好了 TexLive 2014, TexStudio和字体(详细的安装日志见压缩包注释)，开箱即用，下载地址 <http://pan.baidu.com/s/1jGj5uQi>。
