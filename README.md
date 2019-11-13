##程序第三版

####功能说明

本程序实现了菲林自动绘制的功能。具体如下：  
**输入文件：**

* 由HFSS导出的DXF文件。
* 配置文件 `config.ini`  

**输出文件：**  

* 完整的转化后的菲林设计文件。文件格式为DXF，其中包含设计导出的所有图案以及相应的切割线、印刷定位圆环以及叠层对位十字架。
* 菲林说明文档。内容包括：
 * 设计者姓名
 * 设计日期
 * 瓷体对应的设计收缩率
 * 若有2款以上的设计图纸拼网的话，则会给出拼网的方式。即每款型号占据拼网区块中的位置，位于第几行，第几列？
 * 每款设计图纸的型号
 * 每款设计图纸内部图案的放缩方案数量，对应的放缩率值以及分别对应1bar中的设计数量
 * 每款设计图纸在菲林中占据的行列数及其对应行偏移，列偏移量
 * 菲林切割线中心距总长度（提供给IQC检验用）
 * 菲林图稿中的阵列说明  
* 通孔模式说明。内容包括各通孔层对应的通孔数量。
* 各通孔层的坐标文本格式文件,后缀名为txt。
* 各内部图案层与通孔的对应关系示意图（DXF文件格式）
* 通孔设计DXF文件(可选,为采用长通孔工艺方案委外加工使用的通孔DXF文件).
  
####使用方法

**步骤一:确认输入文件的正确性，完备性（可与步骤二一同进行）**   

确认设计工程师导出DXF设计图纸是否满足一下要求，若有一条不满足，请告知设计工程师具体不符点，并要求其修改。      
1. 输出的DXF文件是否已包括所有设计金属层,金属层内部是否包括对应的通孔	
2. DXF文件的坐标原点是否处于`设计外框的正中心`  
3. 各层的设计是否满足设计规则  
4. 所有的内部图形是否都是`多段线`  

**步骤二:记录图形特征**   

1. 打开其中一款型号的DXF设计文件   
2. 判断图形的X方向的引出端是否需要增加假引，若需要增加请记录`假引需要增加在X或者是Y方向`以及`该DXF文件对应设计层名称`。  Y方向的假引程序会自动添加,所以并不需要关注Y方向的引出端情况.
3. 将同一款设计的DXF文件移动到一个新建的文件夹内。将此新建文件夹的名称更改为配置文件中的对应数字.(配置文件参数详解中有说明)
4. 若有其他需要拼网的型号，则重复以上1~3的步骤。
5. 最后在工作目标目录下内会有n个子文件夹，n的数量等于需要拼网制作的型号数量。

**步骤三:拷贝脚本程序、编辑配置文件**  

1. 将`drawfeilin.py`以及`config.ini`两个文件拷贝到工作目标目录下。
2. 打开`config.ini`文件，并根据实际要求，逐项填写修改并保存`config.ini`文件中的内容。注意参数值请写在`=`后面，参数值与`=`中间可以空格。 `config.ini`文件中各配置参数详解见章节`"配置文件参数详解"` 内容如下所示：  
```
﻿﻿[DEFAULT]

菲林转化者姓名=	苏柯铭
瓷体X方向收缩率=0.85  
瓷体Y方向收缩率=0.85
内部图案X方向中心收缩率=0.85
内部图案Y方向中心收缩率=0.85   
放缩率数量=	7
X方向放缩率差值=	0.01
Y方向放缩率差值=0.01
产品设计x方向长度=	1.5
产品设计y方向长度=	2.03
菲林x方向阵列列数 =	40
菲林y方向阵列列数 =	30
引出端x方向延伸距离=	0.1
引出端y方向延伸距离=	0.1
切割线x方向偏移距离=	50
切割线y方向偏移距离=	50
菲林名称=	SLFL21-0R900G-01-1
MARK旋转角度=90
MARK的X方向偏移=1.2
MARK的Y方向偏移=1.0
MARK文字高度=0.85
表示放缩率的MARK标识=1|2|3|4|5|6|7|8
拼网区块x方向MARK标识=A|B|C|D|E|F|G|H
拼网区块y方向MARK标识=A|B|C|D|E|F|G|H
菲林英寸=8
不做多种放缩的图层=	Mark|Outline
是否绘制通孔层=Yes
是否绘制长通孔DXF文件=Yes
根据通孔绘制PAD=Yes
是否绘制MARK标识=Yes
通孔孔径=0.08
PAD孔径=0.16

[EXTRA]

拼网列分割数=1
拼网行分割数=2
是否镜像图层=Yes
是否切割线内缩=No

[LONGTHROUGHHOLE]
长通孔孔径=0.2
长通孔列表=V1|V2
长通孔模式是否镜像=No

[1]

型号名称=SLFL21-0R900G-01TF
需要做xy方向延伸的图层=L1|G|C3|C1
图层与通孔配对=L1|V1,L2|V2,L3|V3,L4|V4,H1|V4,C1|V4,C2|V5,G|V5
图层与通孔配对(实际)=L1|V1,L2|V2,L3|V3,L4|V4,H1|V4,C1|V4,C2|V5,G|V5
通孔与PAD配对=V1|P1,V2|P2
通孔孔径最大值=0.085

[2]

型号名称=SLFL21-2R700G-01TF
需要做xy方向延伸的图层=
图层与通孔配对=L1|V1,L2|V2,L3|V3,H1|V4,C1|V4
图层与通孔配对(实际)=L1|V1,L2|V2,L3|V3,H1|V4,C1|V4
通孔与PAD配对=V1|P1,V2|P2
通孔孔径最大值=0.085
```

**步骤四:运行脚本文件，编辑菲林**  

1. 运行`drawfeilin.py`  
2. 打开生成的带`(总菲林 )`字样的DXF文件    
3. 逐一打开设计图层，填充内部图案。  (这步可以省略)
4. 将DXF文件另存为合适版本的DWG文件。  (这步可以省略)

至此，所有菲林设计转化的步骤皆已完成。 

####配置文件参数详解

* `菲林转化者姓名`顾名思义，不做解释
* `瓷体X方向收缩率`，`瓷体Y方向收缩率`为对应的瓷体材料XY方向的实际收缩率，一般其参数值相同。
* `内部图案X方向中心放缩率`,`内部图案Y方向中心收缩率`分别为内部图案的X、Y方向中心收缩率，一般设定与瓷体的收缩率一致。
* `放缩率数量`，`X方向放缩率差值`，`Y方向放缩率差值`以给定的差值计算出一个数量为放缩率数量的收缩率数值等差数列后。内部图案会根据此数列的收缩率进行放大。
* `产品设计x方向长度`，`产品设计y方向长度`为设计DXF文件中外框的X、Y方向的长度，单位为mm。
* `菲林x方向阵列列数`，`菲林y方向阵列列数`为菲林设计中对应的X方向阵列列数以及Y方向阵列行数。
* `引出端x方向延伸距离`，`引出端y方向延伸距离`为需要补假引的设计层中引出端图案分别向X、Y方向延伸的距离，单位为mm。
* `切割线x方向偏移距离`，`切割线y方向偏移距离`为绘制的切割左下角印刷定位圆环中心点与生成的DXF总菲林文件的坐标原点的偏移距离，一般不更改此两项参数。
* `菲林名称`顾名思义，不做解释
* `MARK旋转角度`，`MARK的X方向偏移`，`MARK的Y方向偏移`为MARK标识的旋转角度以及其锚点相对于设计外框左下角的x、y方向偏移量，单位同样为mm;其高度等于给定的 MARK文字高度.
* `表示放缩率的MARK标识`为标识不同收缩率方案使用的标识，标识必须使用字母或者数字,标识之间用|相隔开,列表中的标识数量`必须`大于前面给定的放缩率数量.
* `拼网区块x方向MARK标识`以及`拼网区块y方向MARK标识`为识别每款拼网型号的MARK标识,同放缩率的MARK标识,标识也必须使用字母或者数字,标识之间用|相隔开,列表中的标识数量必须大于给定的拼网行列分割数.
* `菲林英寸`为制作菲林的尺寸.一般的或只能填写6或者8.填写其他整数也可以工作,但是这毫无意义.
* `不做多种放缩的图层`某些特定的图层形状不需要做多种放缩，这些图层的放缩率与瓷体收缩率一致。默认设定中包含了Mark层以及Outline层，若要添加新的图层，请将其名称间用`|`相隔开，并保证其名称`必须`与设计DXF文件名一致。
* `是否绘制通孔层`若为Yes则会在菲林文件中绘制通孔层,若为No则不绘制通孔层.
* `是否绘制长通孔DXF文件`若为Yes则会输出指定通孔层的长通孔文件(文件 为DXF格式,且内部的通孔以圆形表示),若为No则不绘制长通孔文件.
* `根据通孔绘制PAD`若为Yes则会绘制给定的通孔层对应的PAD,PAD的大小由`PAD孔径`指定.通孔层与给定的PAD名称对应关系见`通孔与PAD配对`部分.
* `是否绘制MARK标识`若为Yes则会在MARK层绘制区分方案用的MARK标识.
* `通孔孔径`为通孔的模型设计值,用于绘制盛雄激光的开孔模式
* `长通孔列表`为需要绘制长通孔文件的通孔图案层名称列表,其名称间用`|`相隔开，并保证其名称`必须`与设计DXF文件名一致。`长通孔孔径`为绘制的内部通孔圆形的直径.`长通孔模式是否镜像`若为Yes则镜像整个长通孔模式.用于反面机械开孔.
* `拼网列分割数`,`拼网行分割数`为拼网的型号在菲林的行列分布数,两者的乘积必须等于工作目标目录下的子文件夹数量.
* `是否镜像图层`为菲林内部图案需要镜像,若为Yes,则需要的dxf文件会左右镜像后再进行处理.
* `是否切割线内缩`为切割与定位孔的对齐方式,若为Yes,则切割线外侧与定位孔中心对齐,若为No,则是内侧对齐.
* 最下方的用`[]`括起的数字,请将每个设计型号所在的文件夹名称改为这个数字,然后在下方对应的`型号名称`中填入该型号的名称.
* `需要做xy方向延伸的图层`设计DXF中未设计有假引，需要额外补充假引得图层名称请填写与此处。同上，其名称间用`|`相隔开，并保证其名称`必须`与设计DXF文件名一致。
* `图层与通孔配对`这里请按以下格式填写:每组配对请用英文的,(逗号)相隔开,然后每组配对金属图案层名称写在前面,通孔图案层写在后面,两者用|相隔开.注意图层名称`必须`与设计DXF文件名一致
* `图层与通孔配对(实际)`同上,为实际的配对.因为目前叠层是反扣进行的,所以实际对应的关系是本层电极对应上一层的通孔.
* `通孔与PAD配对`这里请按以下格式填写:每组配对请用英文的,(逗号)相隔开,然后每组配对通孔图案层名称写在前面,PAD的名称写在后面,两者用|相隔开.注意图层名称`必须`与设计DXF文件名一致
* `通孔孔径最大值`请测量图形内部通孔的直径,然后加上0.005,单位为mm.