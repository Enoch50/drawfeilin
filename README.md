##程序第一版

####功能说明

本程序实现了菲林自动绘制的功能。具体如下：  
**输入文件：**

* 由HFSS导出的处理过的DXF文件。
* 配置文件 `config.ini`  

**输出文件：**  

* 完整的转化后的菲林设计文件。文件格式为DXF，其中包含设计导出的所有图案以及相应的切割线、印刷定位圆环以及叠层对位十字架。
* 菲林说明文档。内容包括：
 * 设计者姓名
 * 设计日期
 * 设计放缩方案及其对应的放缩率
 * 瓷体对应的设计收缩率
 * 菲林中每个单元行列数及其对应行偏移，列偏移量
 * 菲林切割线中心距总长度（提供给IQC检验用）
 * 菲林图稿中的阵列说明  
* 通孔模式说明。内容包括各通孔层对应的通孔数量。
* 各通孔层的坐标文件。
  
####使用方法

**步骤一:确认输入文件的正确性，完备性（可与步骤二一同进行）**   

确认设计工程师导出DXF设计图纸是否满足一下要求，若有一条不满足，请告知设计工程师具体不符点，并要求其修改。      
1. 输出的DXF文件是否已包括所有设计层，包括通孔层。（若仅无通孔层，可自行添加）
2. DXF文件的坐标原点是否处于`设计外框的正中心`  
3. 各层的设计是否满足设计规则  
4. 所有的内部图形是否都是`多段线`  

**步骤二:修改DXF文件，并记录图形特征**   

1. 打开DXF设计文件  
2. 去掉设计外框  
3. 去掉多余的图案`（根据实际情况）`  
4. 判断是否需要增加假引，若需要增加请记录`假引需要增加在X或者是Y方向`以及`该DXF文件对应设计层名称`。  
5. 将文件另存为`DXF2004格式`，并将文件名更改为合适的名称。对应内电极层的文件可以参照设计工程师导出的文件名，一般不做修改；而对应通孔层的文件请按照作业指导书，将其改为字母`v`或者`V`开头+`数字`的组合。

**步骤三:拷贝脚本程序、编辑配置文件**  

1. 将`drawfeilin.py`以及`config.ini`两个文件拷贝到DXF文件所在的目录下。  
2. 打开`config.ini`文件，并根据实际要求，修改并保存`config.ini`文件中的内容。注意参数值请写在`=`后面，参数值与`=`中间可以空格。 `config.ini`文件中各配置参数详解见章节`"配置文件参数详解"` 内容如下所示：  
```
﻿[DEFAULT]

菲林转化者姓名=	苏柯铭
瓷体X方向收缩率=	0.84  
瓷体Y方向收缩率=0.84       
放缩率数量=	7
X方向放缩率差值=	0.01
Y方向放缩率差值=0.01
产品设计x方向长度=	4.3
产品设计y方向长度=	4.8
菲林x方向阵列列数 =	20
菲林y方向阵列列数 =	20
引出端x方向延伸距离=	0.1
引出端y方向延伸距离=	0.1
切割线x方向偏移距离=	100
切割线y方向偏移距离=	100
定位圆环中心距=	171.68
菲林名称=	SLFL21-0R900G-01-1
MARK旋转角度=90
MARK的X方向偏移=2
MARK的Y方向偏移=2
不做多种放缩的图层=	Mark|Outline
需要做xy方向延伸的图层=
```

**步骤四:运行脚本文件，编辑菲林**  

1. 运行`drawfeilin.py`  
2. 打开生成的带`(总菲林 )`字样的DXF文件  
3. 打开生成的`菲林说明文档.txt`文件，将菲林阵列相关的说明文字复制到以上DXF文件的`0`图层内。  
4. 逐一打开设计图层，填充内部图案。  
5. 将DXF文件另存为合适版本的DWG文件。  

至此，所有菲林设计转化的步骤皆已完成。 

####配置文件参数详解

* `菲林转化者姓名`顾名思义，不做解释
* `瓷体X方向收缩率`，`瓷体Y方向收缩率`为对应的瓷体材料XY方向的实际收缩率，一般其参数值相同。
* `放缩率数量`，`X方向放缩率差值`，`Y方向放缩率差值`已以上的瓷体收缩率为中心值，按照差值生成其中包含`放缩率数量`个数数值的放缩率等差数列。
* `产品设计x方向长度`，`产品设计y方向长度`为设计DXF文件中外框的X、Y方向的长度，单位为mm。
* `菲林x方向阵列列数`，`菲林y方向阵列列数`为菲林设计中对应的X方向阵列列数以及Y方向阵列行数。
* `引出端x方向延伸距离`，`引出端y方向延伸距离`为需要补假引的设计层中引出端图案分别向X、Y方向延伸的距离，单位为mm。
* `切割线x方向偏移距离`，`切割线y方向偏移距离`为绘制的切割左下角印刷定位圆环中心点与生成的DXF总菲林文件的坐标原点的偏移距离，一般不更改此两项参数。
* `定位圆环中心距`为区分六英寸或者八英寸的参数。目前程序只有绘制八英寸菲林的功能，故此项暂不修改。
* `菲林名称`顾名思义，不做解释
* `MARK旋转角度`，`MARK的X方向偏移`，`MARK的Y方向偏移`为MARK标识的旋转角度以及其锚点相对于设计外框左下角的x、y方向偏移量，单位同样为mm。
* `不做多种放缩的图层`某些特定的图层形状不需要做多种放缩，这些图层的放缩率与瓷体收缩率一致。默认设定中包含了Mark层以及Outline层，若要添加新的图层，请将其名称间用`|`相隔开，并保证其名称与设计DXF文件名一致。
* `需要做xy方向延伸的图层`设计DXF中未设计有假引，需要额外补充假引得图层名称请填写与此处。同上，其名称间用`|`相隔开，并保证其名称与设计DXF文件名一致。