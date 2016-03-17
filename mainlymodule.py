# coding:utf-8
import os
import sys
import re
#reading file 
readfilelist=[]
#writefilelist=[]
mypath=os.path.dirname(sys.argv[0])
mypath=os.path.abspath(mypath)
os.chdir(mypath)
filelist= os.listdir(mypath)

#全局变量，后期会形成配置文件

#图形数量以及阵列个数
center_ratio=0.84
ratio_num=7
x_length=4.3
y_length=4.8
x_array_num=30
y_array_num=30
xarray_length=15
yarray_length=10
x_extend_length=0.1
y_extend_length=0.1
name_of_feilin="caonima"

x_blank=(171.68-x_length*x_array_num)/2
y_blank=(171.68-y_length*y_array_num)/2

#切割线绘制相关                   

Is_8inch=True
Is_6inch=False

def drawcutline(d):
    """draw the cutline of feilin
    """
    feilin=file(name_of_feilin+'.dxf','w') 
    feilin.write("0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n70\n2\n") 
    layernamelist=list(d.viewkeys())
    layernamelist=[layernamelist[0]]               
    polycount=0                      #为绘制的多段线计数
    feilin_name_pos=[70.0,175.0]
    ringlist=[[[-0.215,0.0],[0.215,0.0]],[[-0.215,171.68],[0.215,171.68]],[[-0.215,175.68],[0.215,175.68]],[[171.4650,0.0],[171.8950,0.0]],[[171.4650,171.68],[171.8950,171.68]]]
    flashlist=buildflashlist()
    cutlineset=buildcutlineset()
                                    #图层名称与颜色号的对应字典
    
    for layername in layernamelist:
        feilin.write("0\nLAYER\n2\n"+layername+"\n70\n0\n62\n"+str(2)+"\n6\nCONTINUOUS\n")
    feilin.write("0\nENDTAB\n0\nENDSEC\n")            #绘制图层表     
    
    feilin.write("0\nSECTION\n2\nBLOCKS\n")            #绘制块定义
    feilin.write("0\nBLOCK\n8\n0\n2\nROUND_1\n70\n0\n10\n0.0\n20\n0.0\n30\n0.0\n")
    feilin.write("0\nPOLYLINE\n8\n0\n5\n"+""+"\n66\n1\n10\n0.0\n20\n0.0\n30\n0.0\n70\n1\n")
    feilin.write("40\n0.04\n41\n0.04")
    feilin.write("\n0\nVERTEX\n5\n406\n8\n0\n10\n-0.02\n20\n0.0\n30\n0.0\n42\n1.0")
    feilin.write("\n0\nVERTEX\n5\n407\n8\n0\n10\n0.02\n20\n0.0\n30\n0.0\n42\n1.0\n0\nSEQEND\n5\n408\n8\n0\n")
    feilin.write("0\nENDBLK\n5\n43\n8\n0\n")  
    feilin.write("0\nBLOCK\n8\n0\n2\n*U1\n")
                  
    feilin.write("70\n1\n10\n0.0\n20\n0.0\n30\n0.0\n") 
    feilin.write("0\nTEXT\n5\n46\n8\nCUTLINE\n6\nCONTINUOUS\n10\n"+str(feilin_name_pos[0])+"\n20\n"+str(feilin_name_pos[1])+"\n30\n0.0\n")
    feilin.write("40\n2.5\n1\n"+name_of_feilin+"\n0\nENDBLK\n5\n47\n8\n0\n")
    feilin.write("0\nENDSEC\n")
    feilin.write("0\nSECTION\n2\nENTITIES\n")
    for layername in layernamelist:
        for polyline in cutlineset:
            polycount=polycount+1
            feilin.write("0\nPOLYLINE\n8\n"+layername+"\n5\n"+hex(polycount)[2:])         # begin writing a polyline
            feilin.write("\n66\n1\n10\n0.0\n20\n0.0\n30\n0.0\n40\n0.08\n41\n0.08\n")
            polycount=drawwidthpolyline(polyline, polycount, feilin,layername)
        polycount=drawring(ringlist, polycount, feilin, layername)
        polycount=drawflash(flashlist, polycount, feilin, layername)
    
    feilin.write("0\nENDSEC\n0\nEOF\n")                  # write the end of file
    feilin.close()    

def buildcutlineset():
    """build cutline polyline set
    """
    cutlineset=[[[-3.2697,-3.2697],[-4.3304,-4.3304]],[[-3.2697,-4.3304],[-4.3304,-3.2697]]]
    cutlineset.extend([[[-3.2697,176.0104],[-4.3304,174.9497]],[[-3.2697,174.9497],[-4.3304,176.0104]]])
    cutlineset.extend([[[176.0104,176.0104],[174.9497,174.9497]],[[176.0104,174.9497],[174.9497,176.0104]]])
    cutlineset.extend([[[175.4800,-3.05],[175.4800,-4.55]],[[174.7300,-3.8],[176.2300,-3.8]]])
    for row in range(0,x_array_num):
        cutlineset.append([[x_blank+row*x_length,0.0],[x_blank+row*x_length,-3.0]])
        cutlineset.append([[x_blank+row*x_length,171.68],[x_blank+row*x_length,174.68]])
    for line in range(0,y_array_num):
        cutlineset.append([[0.0,y_blank+line*y_length],[-3.0,y_blank+line*y_length]])
        cutlineset.append([[171.68,y_blank+line*y_length],[174.68,y_blank+line*y_length]])
    return cutlineset

def buildflashlist():
    """build flash set
    """
         
    flashlist=[[-3.2697,-3.2697],[-4.3304,-4.3304],[-3.2697,-4.3304],[-4.3304,-3.2697]]
    flashlist.extend([[-3.2697,176.0104],[-4.3304,174.9497],[-3.2697,174.9497],[-4.3304,176.0104]])
    flashlist.extend([[176.0104,176.0104],[174.9497,174.9497],[176.0104,174.9497],[174.9497,176.0104]])
    flashlist.extend([[175.4800,-3.05],[175.4800,-4.55],[174.7300,-3.8],[176.2300,-3.8]])
    
    for row in range(0,x_array_num):
        flashlist.append([x_blank+row*x_length,0.0])
        flashlist.append([x_blank+row*x_length,-3.0])
        flashlist.append([x_blank+row*x_length,171.68])
        flashlist.append([x_blank+row*x_length,174.68])
    for line in range(0,y_array_num):
        flashlist.append([0.0,y_blank+line*y_length])
        flashlist.append([-3.0,y_blank+line*y_length])
        flashlist.append([171.68,y_blank+line*y_length])
        flashlist.append([174.68,y_blank+line*y_length])
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
        filetoread=file(readfile,'r')
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
    d["Outline"]=[[[x_length/2,y_length/2],[x_length/2,-y_length/2],[-x_length/2,-y_length/2],[-x_length/2,y_length/2]]]
    return d

            
def outputarraydataset(d):
    """accept polyline dataset and output them by dxf R12 format to an array
    return none """   
    feilin=file(name_of_feilin+'.dxf','w') 
    feilin.write("0\nSECTION\n2\nENTITIES\n")
    Dlist=d.items()                             #将字典转换为数据
    polycount=0                                 #为绘制的多段线计数
    
    for e in Dlist: 
        if e[0]=="Outline":                           
            VariousRatiolist=Arraydataset(xarray_length, ratio_num,e[1])
        elif e[0]=="Mark":
            VariousRatiolist=Arraydataset(xarray_length, ratio_num,e[1])
        else:            
            VariousRatiolist=manipulatedataset_extendver(xarray_length, center_ratio, ratio_num,e[1])        #读取将数据内的key，value组，并将其中的dataset经过manipulatedict函数转换为dataset的数组。                             
        for dataset in VariousRatiolist:
            for polyline in dataset:
                polycount=polycount+1
                feilin.write("0\nPOLYLINE\n8\n"+e[0]+"\n5\n"+hex(polycount)[2:])         # begin writing a polyline
                feilin.write("\n66\n1\n10\n0.0\n20\n0.0\n30\n0.0\n70\n1\n")
                polycount=drawsinglepolyline(polyline, polycount, feilin,e[0])
                    
    feilin.write("0\nENDSEC\n0\nEOF\n")                   # write the end of file
    feilin.close()    

def outputfeilindataset(d):
    """accept polyline dataset and output them by dxf R12 format to feilin 
    return none """    
    
def Arraydataset(offset_x,n,l):   #offset_x=distance between neighbouring dataset polyline n=how much ratio l=polyline dataset
    """accept polyline dataset and enlarged them by n times with certain ratio,move them with an offset
    return a list of polyline list""" 
    polylinelistlist=[]
    polylinelistlist.append(l)
    for plancount in range(1,n+1):
        newdataset=[]
        for polyline in l:
            newpolyline=[]
            for pos in polyline:
                newpolyline.append([pos[0]/center_ratio+offset_x*plancount,pos[1]/center_ratio])
            newdataset.append(newpolyline)
        polylinelistlist.append(newdataset)   
    return polylinelistlist 

def feilindataset(offset_x,n,l):
    """accept polyline dataset and enlarged them by n times with certain ratio,copy the enlarged dataset for several times,with an offset.
    return a list of polyline list    
    """
       

def manipulatedataset_extendver(offset_x,ratio,n,l):   
    """accept polyline dataset and output them by dxf R12 format
    return a list of polyline list
    the vertex on the origin outline will be move the new enlarged outline and according to the x_extend_length or y_extend_length,move outside of the enlarged outline
    """ 
    polylinelistlist=[]
    polylinelistlist.append(l)
    for plancount in range(1,n+1):
        newdataset=[]
        for polyline in l:
            newpolyline=[]
            for pos in polyline:
                pos_x=pos[0]
                pos_y=pos[1]
                if abs((abs(pos_x)-x_length/2))<0.01:                                          #judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline and plus an extene length
                    pos_x=pos[0]/ratio+offset_x*plancount+(abs(pos_x)/pos_x*x_extend_length)               
                else:
                    pos_x=pos[0]/((ratio*100-((n+1)/2-plancount))/100)+offset_x*plancount
                if abs((abs(pos_y)-y_length/2))<0.01:
                    pos_y=pos[1]/ratio+(abs(pos_y)/pos_y*y_extend_length)
                else:
                    pos_y=pos[1]/((ratio*100-((n+1)/2-plancount))/100)                                  
                newpolyline.append([pos_x,pos_y])
            newdataset.append(newpolyline)
        polylinelistlist.append(newdataset)   
    return polylinelistlist


def manipulatedataset_notextendver(offset_x,ratio,n,l):  
    """accept polyline dataset and output them by dxf R12 format
    return a list of polyline list
    the vertex on the origin outline will be moved to the new enlarged outline
    """ 
    polylinelistlist=[]
    polylinelistlist.append(l)
    for plancount in range(1,n+1):
        newdataset=[]
        for polyline in l:
            newpolyline=[]
            for pos in polyline:
                pos_x=pos[0]
                pos_y=pos[1]
                if abs((abs(pos_x)-x_length/2))<0.01:                       #judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline
                    pos_x=pos[0]/ratio+offset_x*plancount
                else:
                    pos_x=pos[0]/((ratio*100-((n+1)/2-plancount))/100)+offset_x*plancount
                if abs((abs(pos_y)-y_length/2))<0.01:                        #judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline
                    pos_y=pos[1]/ratio
                else:
                    pos_y=pos[1]/((ratio*100-((n+1)/2-plancount))/100)                                  
                newpolyline.append([pos_x,pos_y])
            newdataset.append(newpolyline)
        polylinelistlist.append(newdataset)   
    return polylinelistlist

def manipulatedataset_notextend_move_ver(offset_x,ratio,n,l):  
    """accept polyline dataset and output them by dxf R12 format
    return a list of polyline list
    if a polyline has vertex on the origin outline,it will be move to align with the outline.
    """ 
    polylinelistlist=[]
    polylinelistlist.append(l)
    for plancount in range(1,n+1):
        newdataset=[]
        for polyline in l:
            newpolyline=[]
            polytrait=scanpolyline(polyline)
            if polytrait=="poly_is_on_woutline":
                for pos in polyline:
                    pos_x=pos[0]/((ratio*100-((n+1)/2-plancount))/100)+pos[0]/ratio+offset_x*plancount
                    pos_y=pos[1]
                    newpolyline.append([pos_x,pos_y])
                newdataset.append(newpolyline)
        polylinelistlist.append(newdataset)   
    return polylinelistlist



def manipulatedataset_extend_move_ver(offset_x,ratio,n,l):  
    """accept polyline dataset and output them by dxf R12 format
    return a list of polyline list
    if a polyline has vertex on the origin outline,it will be move to align with the outline.and according to the x_extend_length or y_extend_length,move outside of the enlarged outline
    """ 
    polylinelistlist=[]
    polylinelistlist.append(l)
    for plancount in range(1,n+1):
        newdataset=[]
        for polyline in l:
            newpolyline=[]
            for pos in polyline:
                pos_x=pos[0]
                pos_y=pos[1]
                if abs((abs(pos_x)-x_length/2))<0.01:
                    pos_x=pos[0]/ratio+offset_x*plancount
                else:
                    pos_x=pos[0]/((ratio*100-((n+1)/2-plancount))/100)+offset_x*plancount
                if abs((abs(pos_y)-y_length/2))<0.01:
                    pos_y=pos[1]/ratio
                else:
                    pos_y=pos[1]/((ratio*100-((n+1)/2-plancount))/100)                                  
                newpolyline.append([pos_x,pos_y])
            newdataset.append(newpolyline)
        polylinelistlist.append(newdataset)   
    return polylinelistlist


def drawsinglepolyline(l,vcount,f,layername): #l-polyline vcount-vertex count f-file layername-name of layer
    """read a polyline and output dxf format writing to a specific file
    """
    for pos in l:
        vcount=vcount+1
        f.write("0\nVERTEX\n8\n"+layername+"\n5\n"+hex(vcount)[2:]+"\n")           
        f.write('10\n{:.4f}\n20\n{:.4f}\n30\n0.0\n'.format(pos[0],pos[1]))             # write a point 
        #filetowrite.write('X{:07.3f}Y{:07.3f}\n'.format(pos[0],pos[1])) 
    vcount=vcount+1    
    f.write("0\nSEQEND\n8\n"++layername+"\n5\n"+hex(vcount)[2:]+"\n")                             # finished writing a polyline
    return vcount

def scanpolyline(poly):
    """scan a certain polyline and find some traits of it
    return a string indicated if polyline is on outline
    if 
    """
    for pos in poly:
        if (pos[0]-x_length/2)<0.01:
            return "poly_is_on_lwoutline" 
        if (pos[0]+x_length/2)<0.01:    
            return "poly_is_on_lwoutline" 
        if (pos[1]-y_length/2)<0.01:
            return "poly_is_on_loutline"
        if (pos[1]-y_length/2)<0.01:
            return 
        if 1:
            return "poly_is_on_corner"
    return "poly_is_noton_outline"
    
if __name__=='__main__':
    buildfilelist()
    polylinedatasetdict=extractpolylinefromdxf()        
    #outputarraydataset(polylinedatasetdict)
    #outputfeilindataset(polylinedatasetdict)
    drawcutline(polylinedatasetdict)

            
    
    #readme.write('X{:.0f}Y{:.0f}\n'.format(pos[0],pos[1]))     
    #dataset.sort()
    #readme.write(' has {:d} lines\n'.format(len(dataset)))
    
    # for pos in dataset:
        # filetowrite.write('X{:.0f}Y{:.0f}\n'.format(pos[0],pos[1])) 
    # filetoread.close()
    # filetowrite.close()    
    
    
