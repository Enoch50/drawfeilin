# coding:utf-8
import os
import sys
import re
import random
import time
import configparser
#reading file 
readfilelist=[]
#writefilelist=[]
mypath=os.path.dirname(sys.argv[0])
mypath=os.path.abspath(mypath)
os.chdir(mypath)
filelist= os.listdir(mypath)

#全局变量，后期会形成配置文件


#切割线绘制相关                   
Is_8inch=True
Is_6inch=False


class Globalconfig(object):
    """read the config file
    """
    configfilename='config.ini'
    
    def __init__(self): 
    
        self.config = configparser.ConfigParser()
        self.config.read(self.__class__.configfilename)
        
        self.CENTER_RATIO=self.config.getfloat('DEFAULT','瓷体收缩率')
        self.RATIO_NUM=self.config.getint('DEFAULT','放缩率数量')
        self.RATIO_DIFF=self.config.getfloat('DEFAULT','放缩率差值')
        self.X_LENGTH=self.config.getfloat('DEFAULT','产品设计x方向长度')
        self.Y_LENGTH=self.config.getfloat('DEFAULT','产品设计y方向长度')
        self.X_ARRAY_NUM=self.config.getint('DEFAULT','菲林x方向阵列列数')
        self.Y_ARRAY_NUM=self.config.getint('DEFAULT','菲林y方向阵列列数')
        self.X_EXTENDED_LENGTH=self.config.getfloat('DEFAULT','引出端x方向延伸距离')
        self.Y_EXTENDED_LENGTH=self.config.getfloat('DEFAULT','引出端y方向延伸距离')
        self.CUTLINE_X_OFFSET=self.config.getfloat('DEFAULT','切割线x方向偏移距离')
        self.CUTLINE_Y_OFFSET=self.config.getfloat('DEFAULT','切割线y方向偏移距离')
        self.RING_DISTANCE=self.config.getfloat('DEFAULT','定位圆环中心距')
        self.NAME_OF_FEILIN=self.config.get('DEFAULT','菲林名称')
        self.JUSTCOPYLIST=tuple(self.config.get('DEFAULT','不做多种放缩的图层').split('|'))
        self.EXTENDCOPYLIST=tuple(self.config.get('DEFAULT','需要做xy方向延伸的图层').split('|'))
        self.AUTHOR_NAME=self.config.get('DEFAULT','菲林转化者姓名')
        
        self.X_BLANK=(self.RING_DISTANCE-self.X_LENGTH/self.CENTER_RATIO*self.X_ARRAY_NUM)/2
        self.Y_BLANK=(self.RING_DISTANCE-self.Y_LENGTH/self.CENTER_RATIO*self.Y_ARRAY_NUM)/2

def defineTABLESECTION(f,layernamelist):
    """define dxf table section
    """
    
    layercolordict={}
    for layername in layernamelist:
        t=random.randint(10,17)
        layercolordict[layername]=random.randrange(10+t,240+t,10)
        
    layercolordict["Outline"]=1
    layercolordict["Mark"]=5
    layercolordict["Cutline"]=2
    
    f.write("0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n70\n2\n") 
    for layername in layernamelist:
        f.write("0\nLAYER\n2\n"+layername+"\n70\n0\n62\n"+str(layercolordict[layername])+"\n6\nCONTINUOUS\n")
    f.write("0\nENDTAB\n0\nENDSEC\n")   

def defineBLOCKSECTION(f,layernamelist):
    """define dxf BLOCK section
    """
    feilinname_lineheight=2.5
    #note_lineheigh=4
    layercount=0
    feilin_name_pos=[70.0+globalconfig.CUTLINE_X_OFFSET,185.0+globalconfig.CUTLINE_Y_OFFSET]
    #note_pos=[190.0+globalconfig.CUTLINE_X_OFFSET,80.0+globalconfig.CUTLINE_Y_OFFSET]
    f.write("0\nSECTION\n2\nBLOCKS\n")            #绘制块定义
    f.write("0\nBLOCK\n8\n0\n2\nROUND_1\n70\n0\n10\n0.0\n20\n0.0\n30\n0.0\n")
    f.write("0\nPOLYLINE\n8\n0\n5\n3F\n66\n1\n10\n0.0\n20\n0.0\n30\n0.0\n70\n1\n")
    f.write("40\n0.04\n41\n0.04")
    f.write("\n0\nVERTEX\n5\n406\n8\n0\n10\n-0.02\n20\n0.0\n30\n0.0\n42\n1.0")
    f.write("\n0\nVERTEX\n5\n407\n8\n0\n10\n0.02\n20\n0.0\n30\n0.0\n42\n1.0\n0\nSEQEND\n5\n408\n8\n0\n")
    f.write("0\nENDBLK\n5\n43\n8\n0\n")  
    
    for layername in layernamelist:
        layercount=layercount+1
        f.write("0\nBLOCK\n8\n0\n2\n*U"+str(layercount)+"\n")                 
        f.write("70\n1\n10\n0.0\n20\n0.0\n30\n0.0\n") 
        f.write("0\nTEXT\n5\n46\n8\n"+layername+"\n6\nCONTINUOUS\n10\n"+str(feilin_name_pos[0])+"\n20\n"+str(feilin_name_pos[1])+"\n30\n0.0\n")
        f.write("40\n"+str(feilinname_lineheight)+"\n1\n"+globalconfig.NAME_OF_FEILIN+"-"+layername+"\n0\nENDBLK\n5\n47\n8\n"+layername+"\n")
    
#     layercount=layercount+1
#     f.write("0\nBLOCK\n8\n0\n2\n*U"+str(layercount)+"\n")                 
#     f.write("70\n1\n10\n0.0\n20\n0.0\n30\n0.0\n") 
#     f.write("0\nTEXT\n5\n46\n8\n"+layername+"\n6\nCONTINUOUS\n10\n"+str(note_pos[0])+"\n20\n"+str(note_pos[1])+"\n30\n0.0\n")
#     f.write("40\n"+str(note_lineheigh)+"\n1\n")
#     f.write("")
#     f.write("\n0\nENDBLK\n5\n47\n8\n0\n") 
           
    f.write("0\nENDSEC\n")
    
def drawtext(vcount,f,layername,textcount):
    """draw text in cutline
    """
    vcount=vcount+1
    f.write("0\nINSERT\n8\n"+layername+"\n5\n"+hex(vcount)[2:]+"\n6\nCONTINUOUS\n")           
    f.write("2\n*U"+str(textcount)+"\n10\n0.0\n20\n0.0\n30\n0.0\n")
    return vcount

# def drawnote(vcount,f,tc,fl):
#     """draw feilin note
#     """
#     tc=tc+1
#     vcount=vcount+1
#     f.write("0\nINSERT\n8\n0\n5\n"+hex(vcount)[2:]+"\n6\nCONTINUOUS\n")           
#     f.write("2\n*U"+str(tc)+"\n10\n0.0\n20\n0.0\n30\n0.0\n")
#     
#     return vcount

def drawcutline(f,layernamelist,cutline_entities_count):
    """draw the cutline of feilin
    """ 
      
    #layernamelist=[layernamelist[0]]               
    layercount=0
    ringlist=[[[-0.215+globalconfig.CUTLINE_X_OFFSET,0.0+globalconfig.CUTLINE_Y_OFFSET],[0.215+globalconfig.CUTLINE_X_OFFSET,0.0+globalconfig.CUTLINE_Y_OFFSET]],
              [[-0.215+globalconfig.CUTLINE_X_OFFSET,171.68+globalconfig.CUTLINE_Y_OFFSET],[0.215+globalconfig.CUTLINE_X_OFFSET,171.68+globalconfig.CUTLINE_Y_OFFSET]],
              [[-0.215+globalconfig.CUTLINE_X_OFFSET,175.68+globalconfig.CUTLINE_Y_OFFSET],[0.215+globalconfig.CUTLINE_X_OFFSET,175.68+globalconfig.CUTLINE_Y_OFFSET]],
              [[171.4650+globalconfig.CUTLINE_X_OFFSET,0.0+globalconfig.CUTLINE_Y_OFFSET],[171.8950+globalconfig.CUTLINE_X_OFFSET,0.0+globalconfig.CUTLINE_Y_OFFSET]],
              [[171.4650+globalconfig.CUTLINE_X_OFFSET,171.68+globalconfig.CUTLINE_Y_OFFSET],[171.8950+globalconfig.CUTLINE_X_OFFSET,171.68+globalconfig.CUTLINE_Y_OFFSET]]]
    flashlist=buildflashlist()
    cutlineset=buildcutlineset()                                 
    
    f.write("0\nSECTION\n2\nENTITIES\n")
    
    for layername in layernamelist:
        layercount=layercount+1
        for polyline in cutlineset:
            cutline_entities_count=cutline_entities_count+1
            f.write("0\nPOLYLINE\n8\n"+layername+"\n5\n"+hex(cutline_entities_count)[2:])         # begin writing a polyline
            f.write("\n66\n1\n10\n0.0\n20\n0.0\n30\n0.0\n40\n0.08\n41\n0.08\n")
            cutline_entities_count=drawwidthpolyline(polyline, cutline_entities_count, f,layername)
        cutline_entities_count=drawring(ringlist, cutline_entities_count, f, layername)
        cutline_entities_count=drawflash(flashlist, cutline_entities_count, f, layername)
        cutline_entities_count=drawtext(cutline_entities_count, f, layername,layercount)
    
    return cutline_entities_count

def buildcutlineset():
    """build cutline polyline set
    """
    cutlineset=[[[-3.2697,-3.2697],[-4.3304,-4.3304]],[[-3.2697,-4.3304],[-4.3304,-3.2697]]]
    cutlineset.extend([[[-3.2697,176.0104],[-4.3304,174.9497]],[[-3.2697,174.9497],[-4.3304,176.0104]]])
    cutlineset.extend([[[176.0104,176.0104],[174.9497,174.9497]],[[176.0104,174.9497],[174.9497,176.0104]]])
    cutlineset.extend([[[175.4800,-3.05],[175.4800,-4.55]],[[174.7300,-3.8],[176.2300,-3.8]]])
    
    for cutline in cutlineset:
        for pos in cutline:
            pos[0]=pos[0]+globalconfig.CUTLINE_X_OFFSET
            pos[1]=pos[1]+globalconfig.CUTLINE_Y_OFFSET
    
    for row in range(0,globalconfig.X_ARRAY_NUM):
        cutlineset.append([[globalconfig.X_BLANK+row*(globalconfig.X_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_X_OFFSET,0.0+globalconfig.CUTLINE_Y_OFFSET],[globalconfig.X_BLANK+row*(globalconfig.X_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_X_OFFSET,-3.0+globalconfig.CUTLINE_Y_OFFSET]])
        cutlineset.append([[globalconfig.X_BLANK+row*(globalconfig.X_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_X_OFFSET,171.68+globalconfig.CUTLINE_Y_OFFSET],[globalconfig.X_BLANK+row*(globalconfig.X_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_X_OFFSET,174.68+globalconfig.CUTLINE_Y_OFFSET]])
    for line in range(0,globalconfig.Y_ARRAY_NUM):
        cutlineset.append([[0.0+globalconfig.CUTLINE_X_OFFSET,globalconfig.Y_BLANK+line*(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_Y_OFFSET],[-3.0+globalconfig.CUTLINE_X_OFFSET,globalconfig.Y_BLANK+line*(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_Y_OFFSET]])
        cutlineset.append([[171.68+globalconfig.CUTLINE_X_OFFSET,globalconfig.Y_BLANK+line*(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_Y_OFFSET],[174.68+globalconfig.CUTLINE_X_OFFSET,globalconfig.Y_BLANK+line*(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_Y_OFFSET]])
    return cutlineset

def buildflashlist():
    """build flash set
    """
         
    flashlist=[[-3.2697,-3.2697],[-4.3304,-4.3304],[-3.2697,-4.3304],[-4.3304,-3.2697]]
    flashlist.extend([[-3.2697,176.0104],[-4.3304,174.9497],[-3.2697,174.9497],[-4.3304,176.0104]])
    flashlist.extend([[176.0104,176.0104],[174.9497,174.9497],[176.0104,174.9497],[174.9497,176.0104]])
    flashlist.extend([[175.4800,-3.05],[175.4800,-4.55],[174.7300,-3.8],[176.2300,-3.8]])
    
    for flash in flashlist:
        flash[0]=flash[0]+globalconfig.CUTLINE_X_OFFSET
        flash[1]=flash[1]+globalconfig.CUTLINE_Y_OFFSET
    
    for row in range(0,globalconfig.X_ARRAY_NUM):
        flashlist.append([globalconfig.X_BLANK+row*(globalconfig.X_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_X_OFFSET,0.0+globalconfig.CUTLINE_Y_OFFSET])
        flashlist.append([globalconfig.X_BLANK+row*(globalconfig.X_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_X_OFFSET,-3.0+globalconfig.CUTLINE_Y_OFFSET])
        flashlist.append([globalconfig.X_BLANK+row*(globalconfig.X_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_X_OFFSET,171.68+globalconfig.CUTLINE_Y_OFFSET])
        flashlist.append([globalconfig.X_BLANK+row*(globalconfig.X_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_X_OFFSET,174.68+globalconfig.CUTLINE_Y_OFFSET])
    for line in range(0,globalconfig.Y_ARRAY_NUM):
        flashlist.append([0.0+globalconfig.CUTLINE_X_OFFSET,globalconfig.Y_BLANK+line*(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_Y_OFFSET])
        flashlist.append([-3.0+globalconfig.CUTLINE_X_OFFSET,globalconfig.Y_BLANK+line*(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_Y_OFFSET])
        flashlist.append([171.68+globalconfig.CUTLINE_X_OFFSET,globalconfig.Y_BLANK+line*(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_Y_OFFSET])
        flashlist.append([174.68+globalconfig.CUTLINE_X_OFFSET,globalconfig.Y_BLANK+line*(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO)+globalconfig.CUTLINE_Y_OFFSET])
    return flashlist
    
def drawring(s,vcount,f,layername):#s-ringset vcount-vertex count f-file layername-name of layer 
    """draw ring in cutine
    """
    for l in s:
        vcount=vcount+1
        f.write("0\nPOLYLINE\n8\n"+layername+"\n5\n"+hex(vcount)[2:])
        f.write("\n66\n1\n10\n0.0\n20\n0.0\n30\n0.0\n70\n1\n40\n0.1\n41\n0.1\n")
        for pos in l:
            vcount=vcount+1
            f.write("0\nVERTEX\n8\n"+layername+"\n5\n"+hex(vcount)[2:]+"\n")           
            f.write('10\n{:.4f}\n20\n{:.4f}\n30\n0.0\n42\n1.0\n'.format(pos[0],pos[1]))
        vcount=vcount+1
        f.write("0\nSEQEND\n8\n"+layername+"\n5\n"+hex(vcount)[2:]+"\n") 
    return vcount

def drawflash(l,vcount,f,layername):#l-polyline vcount-vertex count f-file layername-name of layer 
    """draw flash in cutline
    """
    for pos in l:
        vcount=vcount+1
        f.write("0\nINSERT\n8\n"+layername+"\n5\n"+hex(vcount)[2:]+"\n2\nROUND_1\n")           
        f.write('10\n{:.4f}\n20\n{:.4f}\n30\n0.0\n'.format(pos[0],pos[1]))
    vcount=vcount+1
    return vcount
        
def drawwidthpolyline(l,vcount,f,layername): #l-polyline vcount-vertex count f-file layername-name of layer 
    """read a polyline and output dxf format writing to a specific file
    """
    for pos in l:
        vcount=vcount+1
        f.write("0\nVERTEX\n8\n"+layername+"\n5\n"+hex(vcount)[2:]+"\n")           
        f.write('10\n{:.4f}\n20\n{:.4f}\n30\n0.0\n'.format(pos[0],pos[1]))             # write a point 
        #filetowrite.write('X{:07.3f}Y{:07.3f}\n'.format(pos[0],pos[1])) 
    vcount=vcount+1    
    f.write("0\nSEQEND\n8\n"+layername+"\n5\n"+hex(vcount)[2:]+"\n")                             # finished writing a polyline
    return vcount

def buildfilelist():
    """input nothing and return nothing
    """
    for files in filelist:
        if os.path.splitext(files)[1]=='.dxf':   #查找目录下的dxf文件，加入到readfilelist文件列表中 
            readfilelist.append(files)
    #feilin=file('feilin(ph).dxf','w')                 #新建一个文件，名字先占位用，后续改成由配置文件中读入名称。 
    
def extractpolylinefromdxf():
    """extract all polyline from a R12 format dxf file and store them by a list of (vortex list)=polyline 
    return a dictionary,each key of it is the filename of dxf represent the layername of the polyline and the value is the polyline dataset
    """
    d={}
    for readfile in readfilelist:                    #将readfilelist中的文件逐个按照程序进行读取分析
        filetoread=open(readfile,'r')
        layername=filetoread.name.split(".")[0]
        #newfilename=filetoread.name.split('.')[0]+'.txt'
        #readme.write(newfilename)
        #filetowrite=file(newfilename,'w')
        #writefilelist.append(newfilename)                       
        x=0                                               #x坐标
        y=0                                                    #y坐标
        dataset=[]                                          #多段线坐标数组
        counter=0
        xflag=0                                            #以下x、y、poly、end flag表示下一次读取行是否进入表示该变量的行。1为是，0为否。
        yflag=0
        polyflag=0                                          
        endflag=0
        polyline=[]                                       #多段线各顶点坐标构成的数组
        
        
        for line in filetoread.readlines():
            counter += 1
            pattern1=re.compile('AcDbPolyline')              #pattern1~5正则表达式判断是否进入标志行
            pattern2=re.compile('\s{1}10')
            pattern3=re.compile('\s{1}20')
            pattern4=re.compile('\s{2}0')
            pattern5=re.compile('ENDSEC')
            polymatch=pattern1.match(line)
            xmatch=pattern2.match(line)
            ymatch=pattern3.match(line)
            endmatch=pattern4.match(line)
            finalmatch=pattern5.match(line)
            if finalmatch and polyflag==1 and endflag==1:             #实体定义部分结束，将最后一组多段线的顶点坐标数组加入dataset，dataset是该图形中所有多段线的集合
                polyflag=0
                dataset.append(polyline)
                #print(dataset)                                          #打印测试，输出坐标
                #readme.write('polyline has ended!!!')    
            if polyflag==1 and xflag==1 and endflag==0:                #读取X坐标
                x=float(line)
                xflag=0
            if polyflag==1 and yflag==1 and endflag==0:              #读取Y坐标
                y=float(line)
                yflag=0
                polyline.append([x,y])
            if polyflag==1 and len(polyline)>1 and endflag==1:          #读取所有多段线坐标后，将坐标数组加入dataset内
                dataset.append(polyline)
                polyline=[]
                endflag=0
            if endmatch:                          
                endflag=1
            if polymatch:                                  #进入多段线部分，重置其他flag为0。
                polyflag=1
                endflag=0
                xflag=0
                yflag=0
            if xmatch:
                xflag=1
            if ymatch:
                yflag=1  
        
        d[layername]=dataset 
    d["Outline"]=[[[globalconfig.X_LENGTH/2,globalconfig.Y_LENGTH/2],[globalconfig.X_LENGTH/2,-globalconfig.Y_LENGTH/2],[-globalconfig.X_LENGTH/2,-globalconfig.Y_LENGTH/2],[-globalconfig.X_LENGTH/2,globalconfig.Y_LENGTH/2]]]
    return d

            
# def outputarraydataset(d):
#     """accept polyline dataset and output them by dxf R12 format to an array
#     return none """   
#     feilin=file(globalconfig.NAME_OF_FEILIN+'.dxf','w') 
#     feilin.write("0\nSECTION\n2\nENTITIES\n")
#     Dlist=d.items()                             #将字典转换为数据
#     polycount=0                                 #为绘制的多段线计数
#     
#     for e in Dlist: 
#         if e[0]=="Outline":                           
#             VariousRatiolist=Arraydataset(xarraglobalconfig.Y_LENGTH, globalconfig.RATIO_NUM,e[1])
#         elif e[0]=="Mark":
#             VariousRatiolist=Arraydataset(xarraglobalconfig.Y_LENGTH, globalconfig.RATIO_NUM,e[1])
#         else:            
#             VariousRatiolist=manipulatedataset_extendver(xarraglobalconfig.Y_LENGTH, globalconfig.CENTER_RATIO, globalconfig.RATIO_NUM,e[1])        #读取将数据内的key，value组，并将其中的dataset经过manipulatedict函数转换为dataset的数组。                             
#         for dataset in VariousRatiolist:
#             for polyline in dataset:
#                 polycount=polycount+1
#                 feilin.write("0\nPOLYLINE\n8\n"+e[0]+"\n5\n"+hex(polycount)[2:])         # begin writing a polyline
#                 feilin.write("\n66\n1\n10\n0.0\n20\n0.0\n30\n0.0\n70\n1\n")
#                 polycount=drawsinglepolyline(polyline, polycount, feilin,e[0])
#                     
#     feilin.write("0\nENDSEC\n0\nEOF\n")                   # write the end of file
#     feilin.close()    
    
    
def polylinedictarraycopy(d):#d——原始图层多段线字典
    """input a polyline dict and array them by row
    """  
    dictlist=[]
    ratiolist=[]                  #放缩率列表
    rationumaccumulationlist=[]          #放缩率数量累加列表
    
    eachrationum=globalconfig.X_ARRAY_NUM//globalconfig.RATIO_NUM
    leftrationum=globalconfig.X_ARRAY_NUM%globalconfig.RATIO_NUM
    
    eachrationumlist=[eachrationum]*globalconfig.RATIO_NUM          #各个放缩率对应数量的列表
    
    for i in range((globalconfig.RATIO_NUM-1)//2-(leftrationum-1)//2,(globalconfig.RATIO_NUM-1)//2-(leftrationum-1)//2+leftrationum):
        eachrationumlist[i]=eachrationumlist[i]+1           #将整除后的余值加入到靠中间放缩率的方案中。
        
    rationumaccumulationlist.append(0) 
    
    for i in range(1,globalconfig.RATIO_NUM):         #计算放缩率数量累加列表
        rationumaccumulationlist.append(rationumaccumulationlist[i-1]+eachrationumlist[i-1])
    
    for i in range(0,globalconfig.RATIO_NUM):            #计算放缩率列表
        ratiolist.append((globalconfig.CENTER_RATIO-((globalconfig.RATIO_NUM+1)//2-1)*globalconfig.RATIO_DIFF)+i*globalconfig.RATIO_DIFF)    
       
    for i in range(0,globalconfig.RATIO_NUM):        #每种放缩率
        for j in range(0,eachrationumlist[i]):      #每种放缩率对应数量
            newdict={}
            for e in d:                     #将字典中值即每一图层对应的多段线列表进行复制并移动到指定位置
                newdict[e]=polylinedatasetarraycopy(d[e],ratiolist[i],globalconfig.CUTLINE_X_OFFSET+globalconfig.X_BLANK+(rationumaccumulationlist[i]+j+0.5)*globalconfig.X_LENGTH/globalconfig.CENTER_RATIO,globalconfig.CUTLINE_Y_OFFSET+globalconfig.Y_BLANK+0.5*globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO,e,len(dictlist))                     
                #newdict.append([e,polylinedatasetarraycopy(d[e],ratiolist[i],globalconfig.CUTLINE_X_OFFSET+globalconfig.X_BLANK+(rationumaccumulationlist[i]+j+0.5)*globalconfig.X_LENGTH/globalconfig.CENTER_RATIO,globalconfig.CUTLINE_Y_OFFSET+globalconfig.Y_BLANK+0.5*globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO,e,len(dictlist))])
            dictlist.append(newdict)  
    return (dictlist,ratiolist,eachrationumlist)


def holepolylinedictarraycopy(holepolylinedict):
    """input a hole polyline dataset dict and array them by line
    """
    holepolylinearraydict={}
    for e in holepolylinedict:              #对通孔图层多段线字典进行遍历，将里面的多段线向上阵列
        holepolylinedataset=[]
        for row in range(0,globalconfig.Y_ARRAY_NUM):           
            holepolylinedataset.extend(datasetjustcopy(holepolylinedict[e], 1, 0, globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO*row))
        holepolylinearraydict[e]=holepolylinedataset
    return holepolylinearraydict
  
def polylinedatasetarraycopy(l,ratio,x_offset,y_offset,layername,arraycount):
    """copy a polyline dataset and enlarged by a certain ratio
    """ 
    if layername in globalconfig.JUSTCOPYLIST:                      #根据图层名称判断是按中心放缩率直接放大后复制还是按多种放缩率放大后做边上的点的延伸或者不延伸的操作
        dataset=datasetjustcopy(l,globalconfig.CENTER_RATIO,x_offset,y_offset)
    elif layername in globalconfig.EXTENDCOPYLIST:
        dataset=datasetratiocopy_extend(l,ratio,x_offset,y_offset)
    else:
        if arraycount==0:                               #判断是最左边的图案
            dataset=datasetratiocopy_xl_extend(l,ratio,x_offset,y_offset)
        elif arraycount==globalconfig.X_ARRAY_NUM-1:                 #判断是最右边的图案
            dataset=datasetratiocopy_xr_extend(l,ratio,x_offset,y_offset)
        else:                                           #判断是中间的图案  
            dataset=datasetratiocopy_notextend(l,ratio,x_offset,y_offset)
    return dataset
  
def datasetjustcopy(l,ratio,x_offset,y_offset): #l-多段线列表  ratio-放缩比例，基点是原点 x_offset y_offset-移动的偏移
    """just enlarged by center ratio
    """
    dataset=[]
    for polyline in l:
        newpolyline=[]
        for pos in polyline:
            newpolyline.append([pos[0]/ratio+x_offset,pos[1]/ratio+y_offset])
        dataset.append(newpolyline)
    return dataset

def datasetratiocopy_xl_extend(l,ratio,x_offset,y_offset):#只延伸上下两边以及左边的点
    """just enlarged a dataset by certain ratio with vertex on outline extended
    """
    dataset=[]
    for polyline in l:
        newpolyline=[]
        for pos in polyline:
            pos_x=pos[0]
            pos_y=pos[1]
            if abs((abs(pos_x)-globalconfig.X_LENGTH/2))<0.01:
                if pos_x<0:                                          #judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline and plus an extene length
                    pos_x=pos[0]/globalconfig.CENTER_RATIO+(abs(pos_x)/pos_x*globalconfig.X_EXTENDED_LENGTH)+x_offset
                else:
                    pos_x=pos[0]/globalconfig.CENTER_RATIO+x_offset                 
            else:
                pos_x=pos[0]/ratio+x_offset
            if abs((abs(pos_y)-globalconfig.Y_LENGTH/2))<0.01:
                pos_y=pos[1]/globalconfig.CENTER_RATIO+(abs(pos_y)/pos_y*globalconfig.Y_EXTENDED_LENGTH)+y_offset
            else:
                pos_y=pos[1]/ratio+y_offset                              
            newpolyline.append([pos_x,pos_y])
        dataset.append(newpolyline)
    return dataset

def datasetratiocopy_xr_extend(l,ratio,x_offset,y_offset):#只延伸上下两边以及右边的点
    """just enlarged a dataset by certain ratio with vertex on outline extended
    """
    dataset=[]
    for polyline in l:
        newpolyline=[]
        for pos in polyline:
            pos_x=pos[0]
            pos_y=pos[1]
            if abs((abs(pos_x)-globalconfig.X_LENGTH/2))<0.01: 
                if pos_x>0:                                         #judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline and plus an extene length
                    pos_x=pos[0]/globalconfig.CENTER_RATIO+(abs(pos_x)/pos_x*globalconfig.X_EXTENDED_LENGTH)+x_offset
                else:
                    pos_x=pos[0]/globalconfig.CENTER_RATIO+x_offset               
            else:
                pos_x=pos[0]/ratio+x_offset
            if abs((abs(pos_y)-globalconfig.Y_LENGTH/2))<0.01:
                pos_y=pos[1]/globalconfig.CENTER_RATIO+(abs(pos_y)/pos_y*globalconfig.Y_EXTENDED_LENGTH)+y_offset
            else:
                pos_y=pos[1]/ratio+y_offset                              
            newpolyline.append([pos_x,pos_y])
        dataset.append(newpolyline)
    return dataset

def datasetratiocopy_extend(l,ratio,x_offset,y_offset):#全部四边上的点都延伸
    """just enlarged a dataset by certain ratio with vertex on outline extended
    """
    dataset=[]
    for polyline in l:
        newpolyline=[]
        for pos in polyline:
            pos_x=pos[0]
            pos_y=pos[1]
            if abs((abs(pos_x)-globalconfig.X_LENGTH/2))<0.01:                                          #judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline and plus an extene length
                pos_x=pos[0]/globalconfig.CENTER_RATIO+(abs(pos_x)/pos_x*globalconfig.X_EXTENDED_LENGTH)+x_offset               
            else:
                pos_x=pos[0]/ratio+x_offset
            if abs((abs(pos_y)-globalconfig.Y_LENGTH/2))<0.01:
                pos_y=pos[1]/globalconfig.CENTER_RATIO+(abs(pos_y)/pos_y*globalconfig.Y_EXTENDED_LENGTH)+y_offset
            else:
                pos_y=pos[1]/ratio+y_offset                              
            newpolyline.append([pos_x,pos_y])
        dataset.append(newpolyline)
    return dataset
   

def datasetratiocopy_notextend(l,ratio,x_offset,y_offset):#虽然说是不延伸，但是上下两边上的点Y方向还是会延伸的。
    """just enlarged a dataset by certain ratio with vertex on outline not extended
    """
    dataset=[]
    for polyline in l:
        newpolyline=[]
        for pos in polyline:
            pos_x=pos[0]
            pos_y=pos[1]
            if abs((abs(pos_x)-globalconfig.X_LENGTH/2))<0.01:                                          #judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline and plus an extene length
                pos_x=pos[0]/globalconfig.CENTER_RATIO+x_offset               
            else:
                pos_x=pos[0]/ratio+x_offset
            if abs((abs(pos_y)-globalconfig.Y_LENGTH/2))<0.01:
                pos_y=pos[1]/globalconfig.CENTER_RATIO+y_offset+(abs(pos_y)/pos_y*globalconfig.Y_EXTENDED_LENGTH)          #虽然说是不延伸，但是上下两边上的点Y方向还是会延伸的。
            else:
                pos_y=pos[1]/ratio+y_offset                              
            newpolyline.append([pos_x,pos_y])
        dataset.append(newpolyline)
    
    
    return dataset
    
    

def drawpolylinedict(d,f,vcount):
    """draw polyline dict
    """  
    
    for e in d:                  #遍历字典
        for polyline in d[e]:       #遍历字典值，即多段线列表
            vcount=vcount+1
            f.write("0\nPOLYLINE\n8\n"+e+"\n5\n"+hex(vcount)[2:])
            f.write("\n66\n1\n10\n0.0\n20\n0.0\n30\n0.0\n70\n1\n")
            vcount=drawsinglepolyline(polyline, vcount, f,e)          #绘制单独的多段线
    return vcount

def drawfeilin(polylinedatasetdictlist,origindict):#polylinedatasetdictlist-一行中所有图层的字典的列表，其中字典为(key：图层名，value：一个outline中的该图层多段线列表) origindict-原始的未进行操作的字典
    """accept polyline dataset and output them by dxf R12 format to feilin 
    return none """  
    feilin=open(globalconfig.NAME_OF_FEILIN+'(总菲林)'+'.dxf','w')
    layernamelist=list(origindict.keys())
    layernamelist.append("Cutline")   #这里会包括Cutline以及其他除通孔层的图层
                            
    entitiescount=0                                 #为绘制的实体对象计数
    defineTABLESECTION(feilin, layernamelist)
    defineBLOCKSECTION(feilin, layernamelist)
    entitiescount=drawcutline(feilin,layernamelist,entitiescount)
#     entitiescount=drawnote(entitiescount,feilin,len(layernamelist),feilin_list)
    
    for d in polylinedatasetdictlist:                   
        entitiescount=drawpolylinedict(d,feilin,entitiescount)         #对每个字典进行多段线打印
    
    feilin.write("0\nENDSEC\n0\nEOF\n")                  # write the end of file
    feilin.close() 
    #for d in polylinedatasetdictlist:
    
def outputholepos(dictlist,origindict): #dictlist-一行中所有图层的字典的列表，其中字典为(key：图层名，value：一个outline中的该图层多段线列表) origindict-原始的未进行操作的字典
    """read the dict list of arrayed polyline dataset,extrated V hole and array them.and then calculate the hole position
    """
    
    layernamelist=list(origindict.keys())
    
    hole_list=[]
    holepolylinedict={}
    
    for layername in layernamelist:                             #得到通孔层的名称列表
        if layername[0]=='V' or layername[0]=='v':
            hole_list.append(layername)
            
    for holelayer in hole_list:                                 #已经阵列好的第一行中每一层通孔多段线存入新的“通孔名称”-“一行中所有通孔多段线”的字典
        holepolylinelist=[]       
        for d in dictlist:              
            holepolylinelist.extend(d[holelayer])
        holepolylinedict[holelayer]=holepolylinelist
    
    holepolylinearraydict=holepolylinedictarraycopy(holepolylinedict)          #对以上生成的字典进行操作，生成新的字典。字典中对应的值“一行中所有通孔多段线”向上阵列布满整个菲林区域
    
               
    holenotefile=open('通孔模式说明'+'.txt','w')  #输出通孔模式说明
    holenotefile.write("各通孔文件通孔数一览表(不包括5H):\n")
    for e in holepolylinearraydict:
        holeposfile=open(e+'.txt','w')
        centerposlist=calculatecenterpos(holepolylinearraydict[e])
        centerposlist.sort()
        holenotefile.write("通孔层    "+e+"    一共有通孔    "+'{:d}'.format(len(centerposlist))+"    个\n")    #输出每一通孔层的中心点数。即对应通孔数量
        for pos in centerposlist:
            holeposfile.write('X{:.0f}Y{:.0f}\n'.format(pos[0]*1000,pos[1]*1000))                 #要格式化输出，所以先要乘以1000，然后输出小数点前的部分  
        holeposfile.close() 
    
def calculatecenterpos(holepolylinelist):
    """input a hole polyline list and calculate the center position of them,offset by the center of the cutline.
    """
    center_pos_list=[]
    for poly in holepolylinelist:
        center_pos_x=0
        center_pos_y=0
        for pos in poly:                            #通过累加各多段线顶点坐标值，然后除以多段线的顶点数，计算出其中心点的坐标
            center_pos_x=center_pos_x+pos[0]
            center_pos_y=center_pos_y+pos[1]
        center_pos_x=center_pos_x/len(poly)-(globalconfig.CUTLINE_X_OFFSET+globalconfig.RING_DISTANCE/2)
        center_pos_y=center_pos_y/len(poly)-(globalconfig.CUTLINE_Y_OFFSET+globalconfig.RING_DISTANCE/2)
        center_pos_list.append([center_pos_x,center_pos_y])
    return center_pos_list
        
def outputinfo(d,ratiolist,eachrationumlist):
    """output feilin information
    """
    hole_list=[]
    feilin_list=[]
    layernamelist=list(d.keys())
    for layername in layernamelist:             #生成通孔以及菲林的名称列表
        if layername[0]=='V' or layername[0]=='v':
            hole_list.append(layername)
        elif layername!="Outline":
            feilin_list.append(layername)
    

    info=open('菲林说明文件'+'.txt','w')
    info.write(globalconfig.NAME_OF_FEILIN+"丝网设计转化报告\n")
    info.write("转化时间:    "+time.strftime('%Y-%m-%d %A %X',time.localtime(time.time()))+"\n")
    info.write("转化人:     "+globalconfig.AUTHOR_NAME+"\n")
    for i in range(0,globalconfig.RATIO_NUM):
        info.write("放缩方案"+str(i+1)+"——放缩率为    "+'{:.2f}'.format(round(ratiolist[i],2))+"    对应1bar方案数有    "+str(eachrationumlist[i]*globalconfig.Y_ARRAY_NUM)+"\n")
    
    #info.write("放缩方案 : "+str(ratiolist)+"\n")
    #info.write("每个放缩率一行对应数量 : "+str(eachrationumlist)+"\n")
    info.write("瓷体对应放缩率: "+str(globalconfig.CENTER_RATIO)+"\n")
    
    info.write("丝网排列情况: \n")
    info.write("列     "+str(globalconfig.X_ARRAY_NUM)+"×"+'{:.4f}'.format(round(globalconfig.X_LENGTH/globalconfig.CENTER_RATIO,4))+"mm\n")
    info.write("行     "+str(globalconfig.Y_ARRAY_NUM)+"×"+'{:.4f}'.format(round(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO,4))+"mm\n")
    
    info.write("\n\n"+globalconfig.NAME_OF_FEILIN+"菲林检验标准\n")
    info.write("菲林切割线长度检验标准\n")
    info.write("X方向切割线总长度:    "+'{:.4f}'.format(round(globalconfig.X_LENGTH/globalconfig.CENTER_RATIO*globalconfig.X_ARRAY_NUM,4))+"mm\n")
    info.write("Y方向切割线总长度:    "+'{:.4f}'.format(round(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO*globalconfig.Y_ARRAY_NUM,4))+"mm\n")
    #info.write("说明:通孔的图层为"+str(hole_list)+"\n")
    info.write("\n\n菲林设计人:"+globalconfig.AUTHOR_NAME+"\n")
    info.write("菲林设计时间:"+time.strftime('%Y-%m-%d %X',time.localtime(time.time()))+"\n")
    info.write("说明:需要制作菲林的图层为")
    for feilin in feilin_list:
        info.write(feilin+" ")
    info.write("\n阵列方式:请将以上图层图案向上阵列"+str(globalconfig.Y_ARRAY_NUM)+"行，行偏移为"+'{:.4f}'.format(round(globalconfig.Y_LENGTH/globalconfig.CENTER_RATIO,4))+"mm\n")
    info.close()    
      
    
# def Arraydataset(offset_x,n,l):   #offset_x=distance between neighbouring dataset polyline n=how much ratio l=polyline dataset
#     """accept polyline dataset and enlarged them by n times with certain ratio,move them with an offset
#     return a list of polyline list""" 
#     polylinelistlist=[]
#     polylinelistlist.append(l)
#     for plancount in range(1,n+1):
#         newdataset=[]
#         for polyline in l:
#             newpolyline=[]
#             for pos in polyline:
#                 newpolyline.append([pos[0]/globalconfig.CENTER_RATIO+offset_x*plancount,pos[1]/globalconfig.CENTER_RATIO])
#             newdataset.append(newpolyline)
#         polylinelistlist.append(newdataset)   
#     return polylinelistlist 
# 
# def feilindataset(offset_x,n,l):
#     """accept polyline dataset and enlarged them by n times with certain ratio,copy the enlarged dataset for several times,with an offset.
#     return a list of polyline list    
#     """
       

# def manipulatedataset_extendver(offset_x,ratio,n,l):   
#     """accept polyline dataset and output them by dxf R12 format
#     return a list of polyline list
#     the vertex on the origin outline will be move the new enlarged outline and according to the globalconfig.X_EXTENDED_LENGTH or globalconfig.Y_EXTENDED_LENGTH,move outside of the enlarged outline
#     """ 
#     polylinelistlist=[]
#     polylinelistlist.append(l)
#     for plancount in range(1,n+1):
#         newdataset=[]
#         for polyline in l:
#             newpolyline=[]
#             for pos in polyline:
#                 pos_x=pos[0]
#                 pos_y=pos[1]
#                 if abs((abs(pos_x)-globalconfig.X_LENGTH/2))<0.01:                                          #judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline and plus an extene length
#                     pos_x=pos[0]/ratio+offset_x*plancount+(abs(pos_x)/pos_x*globalconfig.X_EXTENDED_LENGTH)               
#                 else:
#                     pos_x=pos[0]/((ratio*100-((n+1)/2-plancount))/100)+offset_x*plancount
#                 if abs((abs(pos_y)-globalconfig.Y_LENGTH/2))<0.01:
#                     pos_y=pos[1]/ratio+(abs(pos_y)/pos_y*globalconfig.Y_EXTENDED_LENGTH)
#                 else:
#                     pos_y=pos[1]/((ratio*100-((n+1)/2-plancount))/100)                                  
#                 newpolyline.append([pos_x,pos_y])
#             newdataset.append(newpolyline)
#         polylinelistlist.append(newdataset)   
#     return polylinelistlist
# 
# 
# def manipulatedataset_notextendver(offset_x,ratio,n,l):  
#     """accept polyline dataset and output them by dxf R12 format
#     return a list of polyline list
#     the vertex on the origin outline will be moved to the new enlarged outline
#     """ 
#     polylinelistlist=[]
#     polylinelistlist.append(l)
#     for plancount in range(1,n+1):
#         newdataset=[]
#         for polyline in l:
#             newpolyline=[]
#             for pos in polyline:
#                 pos_x=pos[0]
#                 pos_y=pos[1]
#                 if abs((abs(pos_x)-globalconfig.X_LENGTH/2))<0.01:                       #judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline
#                     pos_x=pos[0]/ratio+offset_x*plancount
#                 else:
#                     pos_x=pos[0]/((ratio*100-((n+1)/2-plancount))/100)+offset_x*plancount
#                 if abs((abs(pos_y)-globalconfig.Y_LENGTH/2))<0.01:                        #judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline
#                     pos_y=pos[1]/ratio
#                 else:
#                     pos_y=pos[1]/((ratio*100-((n+1)/2-plancount))/100)                                  
#                 newpolyline.append([pos_x,pos_y])
#             newdataset.append(newpolyline)
#         polylinelistlist.append(newdataset)   
#     return polylinelistlist

# def manipulatedataset_notextend_move_ver(offset_x,ratio,n,l):  
#     """accept polyline dataset and output them by dxf R12 format
#     return a list of polyline list
#     if a polyline has vertex on the origin outline,it will be move to align with the outline.
#     """ 
#     polylinelistlist=[]
#     polylinelistlist.append(l)
#     for plancount in range(1,n+1):
#         newdataset=[]
#         for polyline in l:
#             newpolyline=[]
#             polytrait=scanpolyline(polyline)
#             if polytrait=="poly_is_on_woutline":
#                 for pos in polyline:
#                     pos_x=pos[0]/((ratio*100-((n+1)/2-plancount))/100)+pos[0]/ratio+offset_x*plancount
#                     pos_y=pos[1]
#                     newpolyline.append([pos_x,pos_y])
#                 newdataset.append(newpolyline)
#         polylinelistlist.append(newdataset)   
#     return polylinelistlist



# def manipulatedataset_extend_move_ver(offset_x,ratio,n,l):  
#     """accept polyline dataset and output them by dxf R12 format
#     return a list of polyline list
#     if a polyline has vertex on the origin outline,it will be move to align with the outline.and according to the globalconfig.X_EXTENDED_LENGTH or globalconfig.Y_EXTENDED_LENGTH,move outside of the enlarged outline
#     """ 
#     polylinelistlist=[]
#     polylinelistlist.append(l)
#     for plancount in range(1,n+1):
#         newdataset=[]
#         for polyline in l:
#             newpolyline=[]
#             for pos in polyline:
#                 pos_x=pos[0]
#                 pos_y=pos[1]
#                 if abs((abs(pos_x)-globalconfig.X_LENGTH/2))<0.01:
#                     pos_x=pos[0]/ratio+offset_x*plancount
#                 else:
#                     pos_x=pos[0]/((ratio*100-((n+1)/2-plancount))/100)+offset_x*plancount
#                 if abs((abs(pos_y)-globalconfig.Y_LENGTH/2))<0.01:
#                     pos_y=pos[1]/ratio
#                 else:
#                     pos_y=pos[1]/((ratio*100-((n+1)/2-plancount))/100)                                  
#                 newpolyline.append([pos_x,pos_y])
#             newdataset.append(newpolyline)
#         polylinelistlist.append(newdataset)   
#     return polylinelistlist


def drawsinglepolyline(l,vcount,f,layername): #l-polyline vcount-vertex count f-file layername-name of layer
    """read a polyline and output dxf format writing to a specific file
    """
    for pos in l:
        vcount=vcount+1
        f.write("0\nVERTEX\n8\n"+layername+"\n5\n"+hex(vcount)[2:]+"\n")           
        f.write('10\n{:.4f}\n20\n{:.4f}\n30\n0.0\n'.format(pos[0],pos[1]))             # write a point 
        #filetowrite.write('X{:07.3f}Y{:07.3f}\n'.format(pos[0],pos[1])) 
    vcount=vcount+1    
    f.write("0\nSEQEND\n8\n"+layername+"\n5\n"+hex(vcount)[2:]+"\n")                             # finished writing a polyline
    return vcount

# def scanpolyline(poly):
#     """scan a certain polyline and find some traits of it
#     return a string indicated if polyline is on outline
#     if 
#     """
#     for pos in poly:
#         if (pos[0]-globalconfig.X_LENGTH/2)<0.01:
#             return "poly_is_on_lwoutline" 
#         if (pos[0]+globalconfig.X_LENGTH/2)<0.01:    
#             return "poly_is_on_lwoutline" 
#         if (pos[1]-globalconfig.Y_LENGTH/2)<0.01:
#             return "poly_is_on_loutline"
#         if (pos[1]-globalconfig.Y_LENGTH/2)<0.01:
#             return 
#         if 1:
#             return "poly_is_on_corner"
#     return "poly_is_noton_outline"
    
if __name__=='__main__':
    globalconfig=Globalconfig()
    buildfilelist()
    polylinedatasetdict=extractpolylinefromdxf()        
    #outputarraydataset(polylinedatasetdict)
    #outputfeilindataset(polylinedatasetdict)  
    (dictlist,ratiolist,eachrationumlist)=polylinedictarraycopy(polylinedatasetdict)
    drawfeilin(dictlist,polylinedatasetdict)
    outputholepos(dictlist,polylinedatasetdict)
    outputinfo(polylinedatasetdict,ratiolist,eachrationumlist)