# coding:utf-8
import os
import sys
import re
import random
import time
import configparser
import codecs
import copy
import math
from math import sqrt
# reading file


class Globalconfig(object):
    """read the config file and store them in a global object
    """
    configfilename = 'config.ini'

    def __init__(self):

        self.config = configparser.ConfigParser()
        # self.config.read(self.__class__.configfilename)
        self.config.read_file(
            codecs.open(
                self.__class__.configfilename,
                "r+b",
                "utf-8-sig"))
        self.GLOBAL_RATIO = self.config.getfloat('DEFAULT', '图案全局缩放比例')
        self.X_OFFSET = self.config.getfloat('DEFAULT', '图案原点X坐标')
        self.Y_OFFSET = self.config.getfloat('DEFAULT', '图案原点Y坐标')
        self.X_OUTLINE_RATIO = self.config.getfloat('DEFAULT', '瓷体X方向收缩率')
        self.Y_OUTLINE_RATIO = self.config.getfloat('DEFAULT', '瓷体Y方向收缩率')
        self.X_INNER_RATIO = self.config.getfloat('DEFAULT', '内部图案X方向中心收缩率')
        self.Y_INNER_RATIO = self.config.getfloat('DEFAULT', '内部图案Y方向中心收缩率')
        self.RATIO_NUM = self.config.getint('DEFAULT', '放缩率数量')
        self.X_RATIO_DIFF = self.config.getfloat('DEFAULT', 'X方向放缩率差值')
        self.Y_RATIO_DIFF = self.config.getfloat('DEFAULT', 'Y方向放缩率差值')
        self.X_LENGTH = self.config.getfloat('DEFAULT', '产品设计x方向长度')
        self.Y_LENGTH = self.config.getfloat('DEFAULT', '产品设计y方向长度')
        self.X_ARRAY_NUM = self.config.getint('DEFAULT', '菲林x方向阵列列数')
        self.Y_ARRAY_NUM = self.config.getint('DEFAULT', '菲林y方向阵列列数')
        self.X_EXTENDED_LENGTH = self.config.getfloat('DEFAULT', '引出端x方向延伸距离')
        self.Y_EXTENDED_LENGTH = self.config.getfloat('DEFAULT', '引出端y方向延伸距离')
        self.CUTLINE_X_OFFSET = self.config.getfloat('DEFAULT', '切割线x方向偏移距离')
        self.CUTLINE_Y_OFFSET = self.config.getfloat('DEFAULT', '切割线y方向偏移距离')
        self.NAME_OF_FEILIN = self.config.get('DEFAULT', '菲林名称')
        self.JUSTCOPYLIST = tuple(
            self.config.get(
                'DEFAULT',
                '不做多种放缩的图层').split('|'))
        self.AUTHOR_NAME = self.config.get('DEFAULT', '菲林转化者姓名')
        self.MARK_ROTATION_ANGLE = self.config.getint('DEFAULT', 'MARK旋转角度')
        self.MARK_X_OFFSET = self.config.getfloat('DEFAULT', 'MARK的X方向偏移')
        self.MARK_Y_OFFSET = self.config.getfloat('DEFAULT', 'MARK的Y方向偏移')
        self.FEILIN_INCH = self.config.getint('DEFAULT', '菲林英寸')
        self.MARK_HEIGHT = self.config.getfloat('DEFAULT', 'MARK文字高度')
        self.MARKNOTE = self.config.get('DEFAULT', 'MARK标识')
        self.markratiolist = tuple(
            self.config.get(
                'DEFAULT',
                '表示放缩率的MARK标识').split('|'))
        self.blockmark_x_list = tuple(
            self.config.get(
                'DEFAULT',
                '拼网区块x方向MARK标识').split('|'))
        self.blockmark_y_list = tuple(
            self.config.get(
                'DEFAULT',
                '拼网区块y方向MARK标识').split('|'))
        self.DRAWHOLE = self.config.getboolean('DEFAULT', '是否绘制通孔层')
        self.DRAWLONGHOLE = self.config.getboolean('DEFAULT', '是否绘制长通孔DXF文件')
        self.DRAWPAD = self.config.getboolean('DEFAULT', '根据通孔绘制PAD')
        self.DRAWMARKNOTE = self.config.getboolean('DEFAULT', '是否绘制MARK标识')
        self.HOLEDIAMETER = self.config.getfloat('DEFAULT', '通孔孔径')
        self.PADDIAMETER = self.config.getfloat('DEFAULT', 'PAD孔径')

        # self.HOLEMAXDIAMETER=self.config.getfloat('HOLE',u'通孔孔径最大值')
        # self.HOLEEDGENUM=self.config.getfloat('HOLE',u'通孔多边形边数')

        self.LONGHOLELIST = []

        if self.DRAWLONGHOLE:
            self.LONGHOLELIST = tuple(
                self.config.get(
                    'LONGTHROUGHHOLE',
                    '长通孔列表').split('|'))
            self.LONGHOLEDIAMETER = self.config.getfloat(
                'LONGTHROUGHHOLE', '长通孔孔径')
            self.LONGHOLEMIRROR = self.config.getboolean(
                'LONGTHROUGHHOLE', '长通孔模式是否镜像')

        if self.config.get('EXTRA', '拼网列分割数') is not None:
            self.BLOCK_X_NUM = self.config.getint('EXTRA', '拼网列分割数')
        if self.config.get('EXTRA', '拼网行分割数') is not None:
            self.BLOCK_Y_NUM = self.config.getint('EXTRA', '拼网行分割数')

        self.IS_PATTERN_MIRROR = self.config.getboolean('EXTRA', '是否镜像图层')
        self.IS_CUTLINE_SHIFTIN = self.config.getboolean('EXTRA', '是否切割线内缩')

        self.BLOCK_NUM = self.BLOCK_X_NUM * self.BLOCK_Y_NUM
        self.EXTENDCOPYLIST = []
        self.layerholepairdictlist = []
        self.layerholepairdictlist_actual = []
        self.pnlist = []
        self.holemaxdiameterlist = []
        self.holepadpairdictlist = []

        for i in range(0, self.BLOCK_X_NUM * self.BLOCK_Y_NUM):
            self.pnlist.append(self.config.get(str(i + 1), '型号名称'))
            self.EXTENDCOPYLIST.append(
                tuple(self.config.get(str(i + 1), '需要做xy方向延伸的图层').split('|')))
            pairlist = tuple(self.config.get(str(i + 1), '图层与通孔配对').split(','))
            pairlist_actual = tuple(self.config.get(
                str(i + 1), '图层与通孔配对(实际)').split(','))
            self.holemaxdiameterlist.append(
                self.config.getfloat(str(i + 1), '通孔孔径最大值'))
            newpairdict = {}
            for pair in pairlist:
                key, value = pair.split('|')
                newpairdict[key] = value
            self.layerholepairdictlist.append(newpairdict)
            newpairdict2 = {}
            for pair2 in pairlist_actual:
                key, value = pair2.split('|')
                newpairdict2[key] = value
            self.layerholepairdictlist_actual.append(newpairdict2)

            if self.DRAWPAD:
                holepadpairlist = tuple(self.config.get(
                    str(i + 1), '通孔与PAD配对').split(','))
                newholepadpairdict = {}
                for pair in holepadpairlist:
                    key, value = pair.split('|')
                    newholepadpairdict[key] = value
                self.holepadpairdictlist.append(newholepadpairdict)

        self.block_x_accumulationlist = [0]
        self.block_y_accumulationlist = [0]

        self.each_xblock_num = self.X_ARRAY_NUM // self.BLOCK_X_NUM
        self.leftblock_x_num = self.X_ARRAY_NUM % self.BLOCK_X_NUM

        self.each_yblock_num = self.Y_ARRAY_NUM // self.BLOCK_Y_NUM
        self.leftblock_y_num = self.Y_ARRAY_NUM % self.BLOCK_Y_NUM

        self.eachblock_x_list = [self.each_xblock_num] * self.BLOCK_X_NUM
        self.eachblock_y_list = [self.each_yblock_num] * self.BLOCK_Y_NUM

        for i in range(
                self.BLOCK_X_NUM -
                self.leftblock_x_num,
                self.BLOCK_X_NUM):
            self.eachblock_x_list[i] = self.eachblock_x_list[i] + 1

        for i in range(
                self.BLOCK_Y_NUM -
                self.leftblock_y_num,
                self.BLOCK_Y_NUM):
            self.eachblock_y_list[i] = self.eachblock_y_list[i] + 1

        for i in range(1, self.BLOCK_X_NUM):
            self.block_x_accumulationlist.append(
                self.block_x_accumulationlist[i - 1] + self.eachblock_x_list[i - 1])

        for i in range(1, self.BLOCK_Y_NUM):
            self.block_y_accumulationlist.append(
                self.block_y_accumulationlist[i - 1] + self.eachblock_y_list[i - 1])

        if self.FEILIN_INCH == 6:
            self.RING_DISTANCE = 122.4
            self.RING_RADIUS = 0.3
        elif self.FEILIN_INCH == 8:
            self.RING_DISTANCE = 171.68
            self.RING_RADIUS = 0.215
        else:
            self.RING_DISTANCE = self.FEILIN_INCH * 25.4 - 30
            self.RING_RADIUS = 0.215

        self.RING_OFFSET = 3.8
        self.LENGTH_OF_CROSS = 1.5
        self.CUTLINE_LENGTH = 3.0
        self.CUTLINE_WIDTH = 0.08
        self.RING_WIDTH = 0.1
        self.FIFTH_RING_OFFSET = 4.0

        self.X_BLANK = (self.RING_DISTANCE - self.X_LENGTH /
                        self.X_OUTLINE_RATIO * self.X_ARRAY_NUM) / 2
        self.Y_BLANK = (self.RING_DISTANCE - self.Y_LENGTH /
                        self.Y_OUTLINE_RATIO * self.Y_ARRAY_NUM) / 2


class Feilinhole():
    """feilin hole class
    """

    def __init__(self):

        # self.holepolylinearraydict=self.holepolylinedictarraycopy()
        self.holepolylinearraydict = {}

    def calculatecenterpos(self, holepolylinelist):
        center_pos_list = []
        for poly in holepolylinelist:
            center_pos_x = 0
            center_pos_y = 0
            for pos in poly:  # 通过累加各多段线顶点坐标值，然后除以多段线的顶点数，计算出其中心点的坐标
                center_pos_x = center_pos_x + pos[0]
                center_pos_y = center_pos_y + pos[1]
            if globalconfig.FEILIN_INCH == 6:
                center_pos_x = center_pos_x / \
                    len(poly) - globalconfig.CUTLINE_X_OFFSET
                center_pos_y = center_pos_y / \
                    len(poly) - globalconfig.CUTLINE_Y_OFFSET
            else:
                center_pos_x = center_pos_x / \
                    len(poly) - (globalconfig.CUTLINE_X_OFFSET + globalconfig.RING_DISTANCE / 2)
                center_pos_y = center_pos_y / \
                    len(poly) - (globalconfig.CUTLINE_Y_OFFSET + globalconfig.RING_DISTANCE / 2)
            center_pos_list.append([center_pos_x, center_pos_y])
        return center_pos_list

    def calculatecenterposnew(self, holepolylinelist):
        center_pos_list = []
        for poly in holepolylinelist:
            center_pos_x = 0
            center_pos_y = 0
            for pos in poly:  # 通过累加各多段线顶点坐标值，然后除以多段线的顶点数，计算出其中心点的坐标
                center_pos_x = center_pos_x + pos[0]
                center_pos_y = center_pos_y + pos[1]
            center_pos_x = center_pos_x / \
                len(poly) - (globalconfig.CUTLINE_X_OFFSET + globalconfig.RING_DISTANCE / 2)
            center_pos_y = center_pos_y / \
                len(poly) - (globalconfig.CUTLINE_Y_OFFSET + globalconfig.RING_DISTANCE / 2)
            center_pos_list.append([center_pos_x, center_pos_y])
        return center_pos_list

    def calculateholenumber(self):
        return len(self.holeposlist)

    def appendnewblockholedict(self, holepolylinedict, blockcount):
        self.block_x_count = blockcount % globalconfig.BLOCK_X_NUM
        self.block_y_count = blockcount // globalconfig.BLOCK_X_NUM

        newholepolylinearraydict = self.holepolylinedictarraycopy(
            holepolylinedict)
        for e in newholepolylinearraydict:
            if e in list(self.holepolylinearraydict.keys()):
                self.holepolylinearraydict[e].extend(
                    newholepolylinearraydict[e])
            else:
                self.holepolylinearraydict[e] = newholepolylinearraydict[e]

    def holepolylinedictarraycopy(self, holepolylinedict):
        holepolylinearraydict = {}
        for e in holepolylinedict:  # 对通孔图层多段线字典进行遍历，将里面的多段线向上阵列
            holepolylinedataset = []
            for row in range(0,
                             globalconfig.eachblock_y_list[self.block_y_count]):
                holepolylinedataset.extend(
                    datasetjustcopy(
                        holepolylinedict[e],
                        1,
                        1,
                        0,
                        globalconfig.Y_LENGTH /
                        globalconfig.Y_OUTLINE_RATIO *
                        row))
            holepolylinearraydict[e] = holepolylinedataset
        return holepolylinearraydict

    def outputholepos(self):
        holenotefile = open(
            globalconfig.NAME_OF_FEILIN +
            '通孔模式说明' +
            '.txt',
            'w')  # 输出通孔模式说明
        holenotefile.write("各通孔文件通孔数一览表(不包括5H):\n")
        for e in self.holepolylinearraydict:
            holeposfile = open(
                globalconfig.NAME_OF_FEILIN + '-' + e + '.txt', 'w')
            centerposlist = sorted(
                self.calculatecenterposnew(
                    self.holepolylinearraydict[e]))
            holenotefile.write(
                "通孔层    " +
                e +
                "    一共有通孔    " +
                '{:d}'.format(
                    len(centerposlist)) +
                "    个\n")  # 输出每一通孔层的中心点数。即对应通孔数量
            holeposfile.write("T01\nM25\n")
            for pos in centerposlist:
                holeposfile.write(
                    'X{:.0f}Y{:.0f}\n'.format(
                        pos[0] * 1000,
                        pos[1] * 1000))  # 要格式化输出，所以先要乘以1000，然后输出小数点前的部分
            if globalconfig.FEILIN_INCH == 6:
                holeposfile.write(
                    "M01\nR0M02X0\nM02\nM01\nR0M02Y0\nM02\nM08\nT02\nX-61200Y-61200\nX61200Y61200\nX-61200Y61200\nX61200Y-61200\nX-61200Y65200\nM30\n")
            else:
                holeposfile.write(
                    "M01\nR0M02X0\nM02\nM01\nR0M02Y0\nM02\nM08\nT02\nX-85840Y-85840\nX85840Y85840\nX-85840Y85840\nX85840Y-85840\nX-85840Y89840\nM30\n")
            holeposfile.close()

    def outputlongholepos(self):
        for e in self.holepolylinearraydict:
            if e in globalconfig.LONGHOLELIST:
                longholeposfile = file(
                    globalconfig.NAME_OF_FEILIN + '-' + e + '(长通孔)' + '.drl', 'w')
                longholeposfile.write(
                    'M48\nMETRIC\nVER,1\nFMAT,2\nT01C{:.3f}F042B423S6H2000\n'.format(
                        globalconfig.LONGHOLEDIAMETER))  # 内部通孔
                longholeposfile.write('T02C0.2F042B423S6H2000\n')  # 定位孔
                longholeposfile.write('T03C3.175F042B423S6H2000\n')  # 定位孔
                longholeposfile.write('%\n')
                longholeposfile.write('T01\n')
                centerposlist = sorted(
                    self.calculaterlongholecenterposlist_kai(e))
                for pos in centerposlist:
                    longholeposfile.write(
                        'X{:0.0f}Y{:0.0f}\n'.format(
                            pos[0] * 1000,
                            pos[1] * 1000))  # 要格式化输出，所以先要乘以1000，然后输出小数点前的部分
                if globalconfig.FEILIN_INCH == 6:
                    longholeposfile.write('T02\n')
                    if not globalconfig.LONGHOLEMIRROR:
                        longholeposfile.write(
                            "X015000Y015000\nX137400Y015000\nX137400Y137400\nX015000Y137400\nX015000Y141400\n")
                    else:
                        longholeposfile.write(
                            "X015000Y015000\nX137400Y015000\nX137400Y137400\nX015000Y137400\nX137400Y141400\n")
                    longholeposfile.write('T03\n')
                    if not globalconfig.LONGHOLEMIRROR:
                        longholeposfile.write(
                            'X060000Y009000\nX009000Y060000\nX060000Y143400\nX143400Y060000\n')
                    else:
                        longholeposfile.write(
                            'X009000Y060000\nX092400Y009000\nX143400Y060000\nX092400Y143400\n')
                else:
                    longholeposfile.write('T02\n')
                    longholeposfile.write(
                        "X015660Y015660\nX187340Y015660\nX187340Y187340\nX015660Y187340\nX015660Y191340\n")
                    longholeposfile.write('T03\n')
                    longholeposfile.write(
                        'X005660Y085660\nX085660Y005660\nX197340Y085660\nX085660Y197340\n')
                longholeposfile.write('M30')
                longholeposfile.close()

    # 输出长通孔drl文件坐标,坐标原点为默认值
    def calculaterlongholecenterposlist(self, holelayer):
        center_pos_list = []
        for poly in self.holepolylinearraydict[holelayer]:
            center_pos_x = 0
            center_pos_y = 0
            for pos in poly:  # 通过累加各多段线顶点坐标值，然后除以多段线的顶点数，计算出其中心点的坐标
                center_pos_x = center_pos_x + pos[0]
                center_pos_y = center_pos_y + pos[1]
            center_pos_x = center_pos_x / len(poly)
            center_pos_y = center_pos_y / len(poly)
            center_pos_list.append([center_pos_x, center_pos_y])
        return center_pos_list

    # 输出长通孔drl文件坐标,坐标原点为左下角定位孔-15,-15处
    def calculaterlongholecenterposlist_kai(self, holelayer):
        center_pos_list = []
        for poly in self.holepolylinearraydict[holelayer]:
            center_pos_x = 0
            center_pos_y = 0
            for pos in poly:  # 通过累加各多段线顶点坐标值，然后除以多段线的顶点数，计算出其中心点的坐标
                center_pos_x = center_pos_x + pos[0]
                center_pos_y = center_pos_y + pos[1]
            if globalconfig.FEILIN_INCH == 6:
                if not globalconfig.LONGHOLEMIRROR:
                    center_pos_x = center_pos_x / \
                        len(poly) - globalconfig.CUTLINE_X_OFFSET + 15
                    center_pos_y = center_pos_y / \
                        len(poly) - globalconfig.CUTLINE_Y_OFFSET + 15
                else:
                    center_pos_x = 122.4 - \
                        (center_pos_x / len(poly) - globalconfig.CUTLINE_X_OFFSET) + 15
                    center_pos_y = center_pos_y / \
                        len(poly) - globalconfig.CUTLINE_Y_OFFSET + 15
            else:
                if not globalconfig.LONGHOLEMIRROR:
                    center_pos_x = center_pos_x / \
                        len(poly) - globalconfig.CUTLINE_X_OFFSET + 15.66
                    center_pos_y = center_pos_y / \
                        len(poly) - globalconfig.CUTLINE_Y_OFFSET + 15.66
                else:
                    center_pos_x = 171.68 - \
                        (center_pos_x / len(poly) - globalconfig.CUTLINE_X_OFFSET) + 15.66
                    center_pos_y = center_pos_y / \
                        len(poly) - globalconfig.CUTLINE_Y_OFFSET + 15.66
            center_pos_list.append([center_pos_x, center_pos_y])
        return center_pos_list

    def calculateholecenterposlist(self, polylinelist):
        center_pos_list = []
        for poly in polylinelist:
            center_pos_x = 0
            center_pos_y = 0
            for pos in poly:  # 通过累加各多段线顶点坐标值，然后除以多段线的顶点数，计算出其中心点的坐标
                center_pos_x = center_pos_x + pos[0]
                center_pos_y = center_pos_y + pos[1]
            center_pos_x = center_pos_x / len(poly)
            center_pos_y = center_pos_y / len(poly)
            center_pos_list.append([center_pos_x, center_pos_y])
        return center_pos_list


class Feilin_dxfpolyline():
    """each block dxf polyline info class
    """

    def __init__(self, blocknum):
        # self.layercount=len(readfilelist)
        # self.readfilelist=readfilelist
        # self.dictlist={}
        self.x_ratiolist = []
        self.y_ratiolist = []
        # self.polylinedatasetdict=self.extractpoylinefromdxf()
        # self.holepolylinedict={}
        # self.layernamelist=list(self.polylinedatasetdict.viewkeys())
        # self.layernamelist.append("Cutline")   #这里会包括Cutline以及其他除通孔层的图层
        self.hole_list = []
        self.feilin_list = []
        self.layernamelist = []
        self.blocklist = []
        self.layerholepairlist = []
        self.eachrationumlistlist = []
        self.blocknum = blocknum
        self.calculatexyratio()

    def extractpoylinefromdxf(self, readfilelist):
        d = {}
        for readfile in readfilelist:  # 将readfilelist中的文件逐个按照程序进行读取分析
            filetoread = file(readfile, 'r')
            layername = filetoread.name.split("\\")[-1].split(".")[0]
            # newfilename=filetoread.name.split('.')[0]+'.txt'
            # readme.write(newfilename)
            # filetowrite=file(newfilename,'w')
            # writefilelist.append(newfilename)
            x = 0  # x坐标
            y = 0  # y坐标
            dataset = []  # 多段线坐标数组
            counter = 0
            xflag = 0  # 以下x、y、poly、end flag表示下一次读取行是否进入表示该变量的行。1为是，0为否。
            yflag = 0
            polyflag = 0
            endflag = 0
            polyline = []  # 多段线各顶点坐标构成的数组

            for line in filetoread.readlines():
                counter += 1
                # pattern1~5正则表达式判断是否进入标志行
                pattern1 = re.compile('AcDbPolyline')
                pattern2 = re.compile(r'\s{1}10')
                pattern3 = re.compile(r'\s{1}20')
                pattern4 = re.compile(r'\s{2}0')
                pattern5 = re.compile('ENDSEC')
                polymatch = pattern1.match(line)
                xmatch = pattern2.match(line)
                ymatch = pattern3.match(line)
                endmatch = pattern4.match(line)
                finalmatch = pattern5.match(line)
                # 实体定义部分结束，将最后一组多段线的顶点坐标数组加入dataset，dataset是该图形中所有多段线的集合
                if finalmatch and polyflag == 1 and endflag == 1:
                    polyflag = 0
                    dataset.append(polyline)
                    # print(dataset)                                          #打印测试，输出坐标
                    #readme.write('polyline has ended!!!')
                if polyflag == 1 and xflag == 1 and endflag == 0:  # 读取X坐标
                    x = float(line)
                    xflag = 0
                if polyflag == 1 and yflag == 1 and endflag == 0:  # 读取Y坐标
                    y = float(line)
                    yflag = 0
                    polyline.append([x, y])
                if polyflag == 1 and len(
                        polyline) > 1 and endflag == 1:  # 读取所有多段线坐标后，将坐标数组加入dataset内
                    dataset.append(polyline)
                    polyline = []
                    endflag = 0
                if endmatch:
                    endflag = 1
                if polymatch:  # 进入多段线部分，重置其他flag为0。
                    polyflag = 1
                    endflag = 0
                    xflag = 0
                    yflag = 0
                if xmatch:
                    xflag = 1
                if ymatch:
                    yflag = 1

            d[layername] = dataset
        d["Outline"] = [[[globalconfig.X_LENGTH / 2, globalconfig.Y_LENGTH / 2], [globalconfig.X_LENGTH / 2, -globalconfig.Y_LENGTH / 2],
                         [-globalconfig.X_LENGTH / 2, -globalconfig.Y_LENGTH / 2], [-globalconfig.X_LENGTH / 2, globalconfig.Y_LENGTH / 2]]]
        return d

    def extractpoylinefromR12dxf(self, blockcount, readfilelist):
        d = {}
        for readfile in readfilelist:  # 将readfilelist中的文件逐个按照程序进行读取分析
            filetoread = open(readfile, 'r')
            layername = filetoread.name.split("\\")[-1].split(".")[0]

            pattern0 = re.compile(r'ENTITIES')
            pattern1 = re.compile(r'POLYLINE')
            pattern2 = re.compile(r'VERTEX')
            pattern3 = re.compile(r'\s{1}10\n(.*)\n\s{1}20\n(.*)\n')

            dataset = []
            holedataset = []

            # filetowrite=file(layername+'temp.txt','w')
            readcontent = filetoread.read()
            entitiesstr = re.split(pattern0, readcontent)[1]
            polylinelist = re.split(pattern1, entitiesstr)[1:]
            for polylinestr in polylinelist:
                polyline = []
                vertexlist = re.split(pattern2, polylinestr)[1:]
                for vertex in vertexlist:
                    xpos = float(pattern3.search(vertex).group(1)) / \
                        globalconfig.GLOBAL_RATIO - globalconfig.X_OFFSET
                    ypos = float(pattern3.search(vertex).group(2)) / \
                        globalconfig.GLOBAL_RATIO - globalconfig.Y_OFFSET
                    if not globalconfig.IS_PATTERN_MIRROR:
                        polyline.append([xpos, ypos])
                    else:
                        polyline.append([-xpos, ypos])
                    # filetowrite.write(str(xpos)+','+str(ypos)+'\n')

                # 处理掉外框以及通孔
                if self.polylineisoutline(polyline):
                    1
                elif self.polylineishole(blockcount, polyline):
                    if layername in list(
                            globalconfig.layerholepairdictlist[blockcount].keys()):
                        holedataset.append(polyline)
                else:
                    dataset.append(polyline)

                # dataset.append(polyline)
            if layername in list(
                    globalconfig.layerholepairdictlist[blockcount].keys()):
                if globalconfig.layerholepairdictlist[blockcount][layername] not in list(
                        d.keys()):
                    d[globalconfig.layerholepairdictlist[blockcount]
                        [layername]] = holedataset
            d[layername] = dataset
        d["Outline"] = [[[globalconfig.X_LENGTH / 2, globalconfig.Y_LENGTH / 2], [globalconfig.X_LENGTH / 2, -globalconfig.Y_LENGTH / 2],
                         [-globalconfig.X_LENGTH / 2, -globalconfig.Y_LENGTH / 2], [-globalconfig.X_LENGTH / 2, globalconfig.Y_LENGTH / 2]]]

        return d

    def polylineisoutline(self, polyline):
        """
        """
        if len(polyline) == 4:
            xcenterpos = abs(
                polyline[0][0] +
                polyline[1][0] +
                polyline[2][0] +
                polyline[3][0])
            ycenterpos = abs(
                polyline[0][1] +
                polyline[1][1] +
                polyline[2][1] +
                polyline[3][1])

            xlength = abs(polyline[0][0]) + abs(polyline[1][0])
            ylength = abs(polyline[0][1]) + abs(polyline[1][1])

            if xcenterpos < 0.001 and ycenterpos < 0.001 and abs(
                xlength -
                globalconfig.X_LENGTH) < 0.001 and abs(
                ylength -
                    globalconfig.Y_LENGTH) < 0.001:
                return True
            else:
                return False
        else:
            return False

    def polylineishole(self, blockcount, polyline):
        """
        """
        if len(polyline) > 1:
            edgelength = math.sqrt(
                (polyline[0][0] - polyline[1][0])**2 + (polyline[0][1] - polyline[1][1])**2)
        else:
            return False
        for i in range(1, len(polyline) - 1):
            edgelengthi = math.sqrt(
                (polyline[i][0] - polyline[i + 1][0])**2 + (polyline[i][1] - polyline[i + 1][1])**2)
            if abs(edgelengthi - edgelength) > 0.001:
                return False
        if (edgelength / 2) / math.sin(math.pi / len(polyline)) * \
                2 < globalconfig.holemaxdiameterlist[blockcount]:
            return True
        else:
            return False

    def calculatexyratio(self):
        """
        """
        for i in range(0, globalconfig.RATIO_NUM):  # 计算放缩率列表
            self.x_ratiolist.append((globalconfig.X_INNER_RATIO -
                                     ((globalconfig.RATIO_NUM +
                                       1) //
                                      2 -
                                      1) *
                                     globalconfig.X_RATIO_DIFF) +
                                    i *
                                    globalconfig.X_RATIO_DIFF)
            self.y_ratiolist.append((globalconfig.Y_INNER_RATIO -
                                     ((globalconfig.RATIO_NUM +
                                       1) //
                                      2 -
                                      1) *
                                     globalconfig.Y_RATIO_DIFF) +
                                    i *
                                    globalconfig.Y_RATIO_DIFF)

    def polylinedictarraycopy(self, blockcount, polylinedatasetdict):  # d——原始图层多段线字典
        """input a polyline dict and array them by row
        """
        dictlist = []
        rationumaccumulationlist = []  # 放缩率数量累加列表

        block_x_count = blockcount % globalconfig.BLOCK_X_NUM
        block_y_count = blockcount // globalconfig.BLOCK_X_NUM

        # 区块的原点偏移量（相对于outline左下角）
        block_x_offset = globalconfig.block_x_accumulationlist[block_x_count] * \
            globalconfig.X_LENGTH / globalconfig.X_OUTLINE_RATIO
        block_y_offset = globalconfig.block_y_accumulationlist[block_y_count] * \
            globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO

        eachrationum = globalconfig.eachblock_x_list[block_x_count] // globalconfig.RATIO_NUM
        leftrationum = globalconfig.eachblock_x_list[block_x_count] % globalconfig.RATIO_NUM

        if eachrationum == 0:
            print("eachrationum==0,please reduce ratio num!")

        eachrationumlist = [eachrationum] * \
            globalconfig.RATIO_NUM  # 各个放缩率对应数量的列表

        for i in range((globalconfig.RATIO_NUM - 1) // 2 - (leftrationum - 1) // 2,
                       (globalconfig.RATIO_NUM - 1) // 2 - (leftrationum - 1) // 2 + leftrationum):
            eachrationumlist[i] = eachrationumlist[i] + \
                1  # 将整除后的余值加入到靠中间放缩率的方案中。

        rationumaccumulationlist.append(0)

        for i in range(1, globalconfig.RATIO_NUM):  # 计算放缩率数量累加列表
            rationumaccumulationlist.append(
                rationumaccumulationlist[i - 1] + eachrationumlist[i - 1])

        for i in range(0, globalconfig.RATIO_NUM):  # 每种放缩率
            for j in range(0, eachrationumlist[i]):  # 每种放缩率对应数量
                newdict = {}
                for e in polylinedatasetdict:  # 将字典中值即每一图层对应的多段线列表进行复制并移动到指定位置
                    newdict[e] = polylinedatasetarraycopy(
                        polylinedatasetdict[e],
                        self.x_ratiolist[i],
                        self.y_ratiolist[i],
                        globalconfig.CUTLINE_X_OFFSET +
                        globalconfig.X_BLANK +
                        (
                            rationumaccumulationlist[i] +
                            j +
                            0.5) *
                        globalconfig.X_LENGTH /
                        globalconfig.X_OUTLINE_RATIO +
                        block_x_offset,
                        globalconfig.CUTLINE_Y_OFFSET +
                        globalconfig.Y_BLANK +
                        0.5 *
                        globalconfig.Y_LENGTH /
                        globalconfig.Y_OUTLINE_RATIO +
                        block_y_offset,
                        e,
                        len(dictlist),
                        globalconfig.eachblock_x_list[block_x_count],
                        blockcount)
                dictlist.append(newdict)
        return dictlist, eachrationumlist

    def createnewblock(self, blockname, blockcount, readfilelist):
        """createnewblock
        """

        polylinedatasetdict = self.extractpoylinefromR12dxf(
            blockcount, readfilelist)
        holepolylinedict = {}
        feilinpolylinedict = {}
        layernamelist = list(polylinedatasetdict.keys())
        # layernamelist.append("Cutline")   #这里会包括Cutline以及其他除通孔层的图层

        feilin_list = []
        hole_list = []

        for layername in layernamelist:  # 生成通孔以及菲林的名称列表
            if layername[0] == 'V' or layername[0] == 'v':
                hole_list.append(layername)
            elif layername != "Outline":
                feilin_list.append(layername)

        self.feilin_list = list(set(self.feilin_list + feilin_list))
        self.hole_list = list(set(self.hole_list + hole_list))

        self.layernamelist = list(set(self.feilin_list + self.hole_list))

        dictlist, eachrationumlist = self.polylinedictarraycopy(
            blockcount, polylinedatasetdict)

        self.blocklist.append(dictlist)
        self.eachrationumlistlist.append(eachrationumlist)

        for feilinlayer in feilin_list:
            feilinpolylinelist = []
            for d in dictlist:
                feilinpolylinelist.extend(d[feilinlayer])
            feilinpolylinedict[feilinlayer] = feilinpolylinelist

        feilinpolylinelist = []
        for d in dictlist:
            feilinpolylinelist.extend(d["Outline"])
        feilinpolylinedict["Outline"] = feilinpolylinelist

        for holelayer in hole_list:  # 已经阵列好的第一行中每一层通孔多段线存入新的“通孔名称”-“一行中所有通孔多段线”的字典
            holepolylinelist = []
            for d in dictlist:
                holepolylinelist.extend(d[holelayer])
            holepolylinedict[holelayer] = holepolylinelist

        return eachrationumlist, holepolylinedict, feilinpolylinedict

    def createlayerholepair(self, blockname, blockcount, readfilelist):
        """
        """
        polylinedatasetdict = self.extractpoylinefromR12dxf(
            blockcount, readfilelist)
        layernamelist = list(polylinedatasetdict.keys())
        # layernamelist.append("Cutline")   #这里会包括Cutline以及其他除通孔层的图层

        feilin_list = []
        hole_list = []
        notepointdict = {}

        for layername in layernamelist:  # 生成通孔以及菲林的名称列表
            if layername[0] == 'V' or layername[0] == 'v':
                hole_list.append(layername)
            elif layername != "Outline":
                feilin_list.append(layername)

        layerholepairdict = {}
        for count, layer in enumerate(feilin_list):
            layerdataset = datasetjustcopy(
                polylinedatasetdict[layer], 1, 1, 1.5 * globalconfig.X_LENGTH * (
                    count %
                    2), 1.5 * globalconfig.Y_LENGTH * (
                    count / 2))
            holedataset = []
            outlinedataset = datasetjustcopy(
                polylinedatasetdict["Outline"], 1, 1, 1.5 * globalconfig.X_LENGTH * (
                    count %
                    2), 1.5 * globalconfig.Y_LENGTH * (
                    count / 2))
            if layer in list(
                    globalconfig.layerholepairdictlist_actual[blockcount].keys()):
                holedataset = datasetjustcopy(polylinedatasetdict[globalconfig.layerholepairdictlist_actual[blockcount][layer]],
                                              1, 1, 1.5 * globalconfig.X_LENGTH * (count % 2), 1.5 * globalconfig.Y_LENGTH * (count / 2))
                if "Outline" in list(layerholepairdict.keys()):
                    layerholepairdict["Outline"].extend(outlinedataset)
                else:
                    layerholepairdict["Outline"] = outlinedataset
                if layer in list(layerholepairdict.keys()):
                    layerholepairdict[layer].extend(layerdataset)
                else:
                    layerholepairdict[layer] = layerdataset
                if globalconfig.layerholepairdictlist_actual[blockcount][layer] in list(
                        layerholepairdict.keys()):
                    layerholepairdict[globalconfig.layerholepairdictlist_actual[blockcount][layer]].extend(
                        holedataset)
                else:
                    layerholepairdict[globalconfig.layerholepairdictlist_actual[blockcount]
                                      [layer]] = holedataset

                notepointdict[layer +
                              '-' +
                              globalconfig.layerholepairdictlist_actual[blockcount][layer]] = [1.5 *
                                                                                               (count %
                                                                                                2) *
                                                                                               globalconfig.X_LENGTH -
                                                                                               0.5 *
                                                                                               globalconfig.X_LENGTH, (1.5 *
                                                                                                                       (count /
                                                                                                                        2) -
                                                                                                                       0.875) *
                                                                                               globalconfig.Y_LENGTH]
            else:
                if "Outline" in list(layerholepairdict.keys()):
                    layerholepairdict["Outline"].extend(outlinedataset)
                else:
                    layerholepairdict["Outline"] = outlinedataset
                if layer in list(layerholepairdict.keys()):
                    layerholepairdict[layer].extend(layerdataset)
                else:
                    layerholepairdict[layer] = layerdataset
                notepointdict[layer] = [1.5 *
                                        (count %
                                         2) *
                                        globalconfig.X_LENGTH -
                                        0.5 *
                                        globalconfig.X_LENGTH, (1.5 *
                                                                (count /
                                                                 2) -
                                                                0.875) *
                                        globalconfig.Y_LENGTH]

        return layerholepairdict, notepointdict

    def outputfeilininfo(self):
        """
        """
        info = open(globalconfig.NAME_OF_FEILIN + '菲林说明文件' + '.txt', 'w')
        info.write(globalconfig.NAME_OF_FEILIN + "丝网设计转化报告\n")
        info.write(
            "转化时间:    " +
            time.strftime(
                '%Y-%m-%d %A %X',
                time.localtime(
                    time.time())) +
            "\n")
        info.write("转化人:     " + globalconfig.AUTHOR_NAME + "\n")

        info.write("丝网排列情况: \n")
        info.write("列     " +
                   str(globalconfig.X_ARRAY_NUM) +
                   "×" +
                   '{:.4f}'.format(round(globalconfig.X_LENGTH /
                                         globalconfig.X_OUTLINE_RATIO, 4)) +
                   "mm\n")
        info.write("行     " +
                   str(globalconfig.Y_ARRAY_NUM) +
                   "×" +
                   '{:.4f}'.format(round(globalconfig.Y_LENGTH /
                                         globalconfig.Y_OUTLINE_RATIO, 4)) +
                   "mm\n")
        info.write("瓷体X方向对应放缩率: " +
                   str(globalconfig.X_OUTLINE_RATIO) +
                   "    瓷体Y方向对应放缩率: " +
                   str(globalconfig.Y_OUTLINE_RATIO) +
                   "\n\n")
        if self.blocknum > 1:
            info.write("拼网方式区块划分:    \n")
            info.write("列方向一共有" + str(globalconfig.BLOCK_X_NUM) + "列\n")
            info.write("行方向一共有" + str(globalconfig.BLOCK_Y_NUM) + "行\n")
            info.write("一共有" + str(self.blocknum) + "套丝网拼网\n")

        for j in range(0, self.blocknum):
            info.write("第" + str(j + 1) + "套图纸对应P/N型号为" +
                       globalconfig.pnlist[j] + "\n")
            if self.blocknum > 1:
                info.write("位于拼网区块的第" + str((j % globalconfig.BLOCK_X_NUM) + 1) +
                           "列    第" + str((j // globalconfig.BLOCK_X_NUM) + 1) + "行\n")
            info.write(globalconfig.pnlist[j] +
                       "型号的图案占据了菲林" +
                       str(globalconfig.eachblock_x_list[j %
                                                         globalconfig.BLOCK_X_NUM]) +
                       "列     " +
                       str(globalconfig.eachblock_y_list[j //
                                                         globalconfig.BLOCK_X_NUM]) +
                       "行\n")
            info.write("其内部图案放缩方案有以下： \n")
            for i in range(0, globalconfig.RATIO_NUM):
                info.write("放缩方案" +
                           str(i +
                               1) +
                           "——x方向放缩率为    " +
                           '{:.3f}'.format(round(self.x_ratiolist[i], 3)) +
                           "    y方向放缩率为    " +
                           '{:.3f}'.format(round(self.y_ratiolist[i], 3)) +
                           "    对应这款型号的放缩方案数    " +
                           str(self.eachrationumlistlist[j][i] *
                               globalconfig.eachblock_y_list[j //
                                                             globalconfig.BLOCK_X_NUM]) +
                           "\n")
            info.write("1bar上的该型号的设计数量为" +
                       str(globalconfig.eachblock_y_list[j //
                                                         globalconfig.BLOCK_X_NUM] *
                           globalconfig.eachblock_x_list[j %
                                                         globalconfig.BLOCK_X_NUM]) +
                       "\n\n")

        #info.write("放缩方案 : "+str(ratiolist)+"\n")
        #info.write("每个放缩率一行对应数量 : "+str(eachrationumlist)+"\n")

        info.write("\n\n" + globalconfig.NAME_OF_FEILIN + "菲林检验标准\n")
        info.write("菲林切割线长度检验标准\n")
        info.write(
            "X方向切割线总长度:    " +
            '{:.4f}'.format(
                round(
                    globalconfig.X_LENGTH /
                    globalconfig.X_OUTLINE_RATIO *
                    globalconfig.X_ARRAY_NUM,
                    4)) +
            "mm\n")
        info.write(
            "Y方向切割线总长度:    " +
            '{:.4f}'.format(
                round(
                    globalconfig.Y_LENGTH /
                    globalconfig.Y_OUTLINE_RATIO *
                    globalconfig.Y_ARRAY_NUM,
                    4)) +
            "mm\n")
        # info.write("说明:通孔的图层为"+str(hole_list)+"\n")

        info.write("\n\n菲林设计人:" + globalconfig.AUTHOR_NAME + "\n")
        info.write(
            "菲林设计时间:" +
            time.strftime(
                '%Y-%m-%d %X',
                time.localtime(
                    time.time())) +
            "\n")
        info.write("说明:需要制作菲林的图层为")
        for feilin in self.feilin_list:
            info.write(feilin + " ")
        # info.write("\n阵列方式:请将以上图层图案向上阵列"+str(globalconfig.Y_ARRAY_NUM)+"行，行偏移为"+'{:.4f}'.format(round(globalconfig.Y_LENGTH/globalconfig.Y_OUTLINE_RATIO,4))+"mm\n")
        info.write("\n阵列方式:请将以上图层图案\n")
        for line in range(0, globalconfig.BLOCK_Y_NUM):
            info.write("从下至上数，位于第" +
                       str(line +
                           1) +
                       "行outline框中的图案向上阵列" +
                       str(globalconfig.eachblock_y_list[line]) +
                       "行，行偏移为" +
                       '{:.4f}'.format(round(globalconfig.Y_LENGTH /
                                             globalconfig.Y_OUTLINE_RATIO, 4)) +
                       "mm\n")
        if self.blocknum > 1:
            info.write("有部分的图层图案未分布在每一行，故阵列后这些图层的图案不会布满菲林图案区域，此外正常设计，请注意\n")
        info.close()


def buildcutlineset():
    """build cutline polyline set
    """
    cutlineset = []

    crosspointlist = [[-globalconfig.RING_OFFSET,
                       -globalconfig.RING_OFFSET],
                      [-globalconfig.RING_OFFSET,
                       globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE],
                      [globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE,
                       globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE]]

    for crosspoint in crosspointlist:
        cutlineset.append([[crosspoint[0] +
                            globalconfig.LENGTH_OF_CROSS /
                            sqrt(2) /
                            2, crosspoint[1] +
                            globalconfig.LENGTH_OF_CROSS /
                            sqrt(2) /
                            2], [crosspoint[0] -
                                 globalconfig.LENGTH_OF_CROSS /
                                 sqrt(2) /
                                 2, crosspoint[1] -
                                 globalconfig.LENGTH_OF_CROSS /
                                 sqrt(2) /
                                 2]])
        cutlineset.append([[crosspoint[0] +
                            globalconfig.LENGTH_OF_CROSS /
                            sqrt(2) /
                            2, crosspoint[1] -
                            globalconfig.LENGTH_OF_CROSS /
                            sqrt(2) /
                            2], [crosspoint[0] -
                                 globalconfig.LENGTH_OF_CROSS /
                                 sqrt(2) /
                                 2, crosspoint[1] +
                                 globalconfig.LENGTH_OF_CROSS /
                                 sqrt(2) /
                                 2]])

    cutlineset.append([[globalconfig.RING_OFFSET +
                        globalconfig.RING_DISTANCE +
                        globalconfig.LENGTH_OF_CROSS /
                        2, -
                        globalconfig.RING_OFFSET], [globalconfig.RING_OFFSET +
                                                    globalconfig.RING_DISTANCE -
                                                    globalconfig.LENGTH_OF_CROSS /
                                                    2, -
                                                    globalconfig.RING_OFFSET]])
    cutlineset.append([[globalconfig.RING_OFFSET +
                        globalconfig.RING_DISTANCE, -
                        globalconfig.RING_OFFSET +
                        globalconfig.LENGTH_OF_CROSS /
                        2], [globalconfig.RING_OFFSET +
                             globalconfig.RING_DISTANCE, -
                             globalconfig.RING_OFFSET -
                             globalconfig.LENGTH_OF_CROSS /
                             2]])

    # cutlineset=[[[-3.2697,-3.2697],[-4.3304,-4.3304]],[[-3.2697,-4.3304],[-4.3304,-3.2697]]]
    # cutlineset.extend([[[-3.2697,176.0104],[-4.3304,174.9497]],[[-3.2697,174.9497],[-4.3304,176.0104]]])
    # cutlineset.extend([[[176.0104,176.0104],[174.9497,174.9497]],[[176.0104,174.9497],[174.9497,176.0104]]])
    # cutlineset.extend([[[175.4800,-3.05],[175.4800,-4.55]],[[174.7300,-3.8],[176.2300,-3.8]]])

    for cutline in cutlineset:
        for pos in cutline:
            pos[0] = pos[0] + globalconfig.CUTLINE_X_OFFSET
            pos[1] = pos[1] + globalconfig.CUTLINE_Y_OFFSET

    for row in range(0, globalconfig.X_ARRAY_NUM + 1):
        if not globalconfig.IS_CUTLINE_SHIFTIN:
            cutlineset.append([[globalconfig.X_BLANK +
                                row *
                                (globalconfig.X_LENGTH /
                                 globalconfig.X_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_X_OFFSET, 0.0 +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.X_BLANK +
                                                                 row *
                                                                 (globalconfig.X_LENGTH /
                                                                  globalconfig.X_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_X_OFFSET, -
                                                                 globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
            cutlineset.append([[globalconfig.X_BLANK +
                                row *
                                (globalconfig.X_LENGTH /
                                 globalconfig.X_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_X_OFFSET, globalconfig.RING_DISTANCE +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.X_BLANK +
                                                                 row *
                                                                 (globalconfig.X_LENGTH /
                                                                  globalconfig.X_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_X_OFFSET, globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.RING_DISTANCE +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
        else:
            cutlineset.append([[globalconfig.X_BLANK +
                                row *
                                (globalconfig.X_LENGTH /
                                 globalconfig.X_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_X_OFFSET, 0.0 +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.X_BLANK +
                                                                 row *
                                                                 (globalconfig.X_LENGTH /
                                                                  globalconfig.X_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_X_OFFSET, globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
            cutlineset.append([[globalconfig.X_BLANK +
                                row *
                                (globalconfig.X_LENGTH /
                                 globalconfig.X_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_X_OFFSET, globalconfig.RING_DISTANCE +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.X_BLANK +
                                                                 row *
                                                                 (globalconfig.X_LENGTH /
                                                                  globalconfig.X_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_X_OFFSET, -
                                                                 globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.RING_DISTANCE +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
    for line in range(0, globalconfig.Y_ARRAY_NUM + 1):
        if not globalconfig.IS_CUTLINE_SHIFTIN:
            cutlineset.append([[0.0 + globalconfig.CUTLINE_X_OFFSET,
                                globalconfig.Y_BLANK + line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET],
                               [-globalconfig.CUTLINE_LENGTH + globalconfig.CUTLINE_X_OFFSET,
                                globalconfig.Y_BLANK + line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET]])
            cutlineset.append([[globalconfig.RING_DISTANCE +
                                globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                                line *
                                (globalconfig.Y_LENGTH /
                                 globalconfig.Y_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.RING_DISTANCE +
                                                                 globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                                                                 line *
                                                                 (globalconfig.Y_LENGTH /
                                                                  globalconfig.Y_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
        else:
            cutlineset.append([[0.0 +
                                globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                                line *
                                (globalconfig.Y_LENGTH /
                                 globalconfig.Y_OUTLINE_RATIO) +
                                globalconfig.CUTLINE_Y_OFFSET], [globalconfig.CUTLINE_LENGTH +
                                                                 globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                                                                 line *
                                                                 (globalconfig.Y_LENGTH /
                                                                  globalconfig.Y_OUTLINE_RATIO) +
                                                                 globalconfig.CUTLINE_Y_OFFSET]])
            cutlineset.append([[globalconfig.RING_DISTANCE + globalconfig.CUTLINE_X_OFFSET,
                                globalconfig.Y_BLANK + line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET],
                               [-globalconfig.CUTLINE_LENGTH + globalconfig.RING_DISTANCE + globalconfig.CUTLINE_X_OFFSET,
                                globalconfig.Y_BLANK + line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET]])
    return cutlineset


def buildflashlist():
    """build flash set
    """
    flashlist = []
    crosspointlist = [[-globalconfig.RING_OFFSET,
                       -globalconfig.RING_OFFSET],
                      [-globalconfig.RING_OFFSET,
                       globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE],
                      [globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE,
                       globalconfig.RING_OFFSET + globalconfig.RING_DISTANCE]]

    for crosspoint in crosspointlist:
        flashlist.append([crosspoint[0] +
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2, crosspoint[1] +
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2])
        flashlist.append([crosspoint[0] -
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2, crosspoint[1] -
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2])
        flashlist.append([crosspoint[0] +
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2, crosspoint[1] -
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2])
        flashlist.append([crosspoint[0] -
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2, crosspoint[1] +
                          globalconfig.LENGTH_OF_CROSS /
                          sqrt(2) /
                          2])

    flashlist.append([globalconfig.RING_OFFSET +
                      globalconfig.RING_DISTANCE +
                      globalconfig.LENGTH_OF_CROSS /
                      2, -
                      globalconfig.RING_OFFSET])
    flashlist.append([globalconfig.RING_OFFSET +
                      globalconfig.RING_DISTANCE -
                      globalconfig.LENGTH_OF_CROSS /
                      2, -
                      globalconfig.RING_OFFSET])
    flashlist.append([globalconfig.RING_OFFSET +
                      globalconfig.RING_DISTANCE, -
                      globalconfig.RING_OFFSET +
                      globalconfig.LENGTH_OF_CROSS /
                      2])
    flashlist.append([globalconfig.RING_OFFSET +
                      globalconfig.RING_DISTANCE, -
                      globalconfig.RING_OFFSET -
                      globalconfig.LENGTH_OF_CROSS /
                      2])
#     flashlist=[[-3.2697,-3.2697],[-4.3304,-4.3304],[-3.2697,-4.3304],[-4.3304,-3.2697]]
#     flashlist.extend([[-3.2697,176.0104],[-4.3304,174.9497],[-3.2697,174.9497],[-4.3304,176.0104]])
#     flashlist.extend([[176.0104,176.0104],[174.9497,174.9497],[176.0104,174.9497],[174.9497,176.0104]])
#     flashlist.extend([[175.4800,-3.05],[175.4800,-4.55],[174.7300,-3.8],[176.2300,-3.8]])
#
    for flash in flashlist:
        flash[0] = flash[0] + globalconfig.CUTLINE_X_OFFSET
        flash[1] = flash[1] + globalconfig.CUTLINE_Y_OFFSET

    for row in range(0, globalconfig.X_ARRAY_NUM + 1):
        flashlist.append([globalconfig.X_BLANK +
                          row *
                          (globalconfig.X_LENGTH /
                           globalconfig.X_OUTLINE_RATIO) +
                          globalconfig.CUTLINE_X_OFFSET, 0.0 +
                          globalconfig.CUTLINE_Y_OFFSET])
        flashlist.append([globalconfig.X_BLANK +
                          row *
                          (globalconfig.X_LENGTH /
                           globalconfig.X_OUTLINE_RATIO) +
                          globalconfig.CUTLINE_X_OFFSET, globalconfig.RING_DISTANCE +
                          globalconfig.CUTLINE_Y_OFFSET])
        if not globalconfig.IS_CUTLINE_SHIFTIN:
            flashlist.append([globalconfig.X_BLANK +
                              row *
                              (globalconfig.X_LENGTH /
                               globalconfig.X_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_X_OFFSET, -
                              globalconfig.CUTLINE_LENGTH +
                              globalconfig.CUTLINE_Y_OFFSET])
            flashlist.append([globalconfig.X_BLANK +
                              row *
                              (globalconfig.X_LENGTH /
                               globalconfig.X_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_X_OFFSET, globalconfig.CUTLINE_LENGTH +
                              globalconfig.RING_DISTANCE +
                              globalconfig.CUTLINE_Y_OFFSET])
        else:
            flashlist.append([globalconfig.X_BLANK +
                              row *
                              (globalconfig.X_LENGTH /
                               globalconfig.X_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_X_OFFSET, globalconfig.CUTLINE_LENGTH +
                              globalconfig.CUTLINE_Y_OFFSET])
            flashlist.append([globalconfig.X_BLANK +
                              row *
                              (globalconfig.X_LENGTH /
                               globalconfig.X_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_X_OFFSET, -
                              globalconfig.CUTLINE_LENGTH +
                              globalconfig.RING_DISTANCE +
                              globalconfig.CUTLINE_Y_OFFSET])

    for line in range(0, globalconfig.Y_ARRAY_NUM + 1):
        flashlist.append([0.0 +
                          globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                          line *
                          (globalconfig.Y_LENGTH /
                           globalconfig.Y_OUTLINE_RATIO) +
                          globalconfig.CUTLINE_Y_OFFSET])
        flashlist.append([globalconfig.RING_DISTANCE +
                          globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                          line *
                          (globalconfig.Y_LENGTH /
                           globalconfig.Y_OUTLINE_RATIO) +
                          globalconfig.CUTLINE_Y_OFFSET])
        if not globalconfig.IS_CUTLINE_SHIFTIN:
            flashlist.append([-globalconfig.CUTLINE_LENGTH + globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                              line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET])
            flashlist.append([globalconfig.CUTLINE_LENGTH +
                              globalconfig.RING_DISTANCE +
                              globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                              line *
                              (globalconfig.Y_LENGTH /
                               globalconfig.Y_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_Y_OFFSET])
        else:
            flashlist.append([globalconfig.CUTLINE_LENGTH +
                              globalconfig.CUTLINE_X_OFFSET, globalconfig.Y_BLANK +
                              line *
                              (globalconfig.Y_LENGTH /
                               globalconfig.Y_OUTLINE_RATIO) +
                              globalconfig.CUTLINE_Y_OFFSET])
            flashlist.append([-globalconfig.CUTLINE_LENGTH + globalconfig.RING_DISTANCE + globalconfig.CUTLINE_X_OFFSET,
                              globalconfig.Y_BLANK + line * (globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO) + globalconfig.CUTLINE_Y_OFFSET])

    return flashlist


def buildringlist():
    '''build ring list
    '''
    ringlist = [[[-globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  0.0 + globalconfig.CUTLINE_Y_OFFSET],
                 [globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  0.0 + globalconfig.CUTLINE_Y_OFFSET]],
                [[-globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                 [globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET]],
                [[-globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  globalconfig.FIFTH_RING_OFFSET + globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                 [globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                    globalconfig.FIFTH_RING_OFFSET + globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET]],
                [[globalconfig.RING_DISTANCE - globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  0.0 + globalconfig.CUTLINE_Y_OFFSET],
                 [globalconfig.RING_DISTANCE + globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                    0.0 + globalconfig.CUTLINE_Y_OFFSET]],
                [[globalconfig.RING_DISTANCE - globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                  globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                 [globalconfig.RING_DISTANCE + globalconfig.RING_RADIUS + globalconfig.CUTLINE_X_OFFSET,
                    globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET]]]

    return ringlist


def buildringholelist():
    ringholelist = [[globalconfig.CUTLINE_X_OFFSET,
                     globalconfig.CUTLINE_Y_OFFSET],
                    [globalconfig.CUTLINE_X_OFFSET,
                     globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                    [globalconfig.CUTLINE_X_OFFSET,
                     globalconfig.FIFTH_RING_OFFSET + globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                    [globalconfig.RING_DISTANCE + globalconfig.CUTLINE_X_OFFSET,
                     globalconfig.CUTLINE_Y_OFFSET],
                    [globalconfig.RING_DISTANCE + globalconfig.CUTLINE_X_OFFSET,
                     globalconfig.RING_DISTANCE + globalconfig.CUTLINE_Y_OFFSET],
                    ]
    return ringholelist


def buildmarkpointlist(eachrationumlist, blockcount):
    """build mark point list
    """

    markpointlistdict = {}

    markpointlist = []
    rationumaccumulationlist = []
    rationumaccumulationlist.append(0)
    for i in range(1, globalconfig.RATIO_NUM):  # 计算放缩率数量累加列表
        rationumaccumulationlist.append(
            rationumaccumulationlist[i - 1] + eachrationumlist[i - 1])

    block_x_count = blockcount % globalconfig.BLOCK_X_NUM
    block_y_count = blockcount // globalconfig.BLOCK_X_NUM

    block_x_offset = globalconfig.block_x_accumulationlist[block_x_count] * \
        globalconfig.X_LENGTH / globalconfig.X_OUTLINE_RATIO
    block_y_offset = globalconfig.block_y_accumulationlist[block_y_count] * \
        globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO

    for i in range(len(eachrationumlist)):
        markpointlist = []
        for row in range(0, eachrationumlist[i]):
            markpointlist.append([globalconfig.X_BLANK +
                                  globalconfig.CUTLINE_X_OFFSET +
                                  (globalconfig.X_LENGTH /
                                   globalconfig.X_OUTLINE_RATIO) *
                                  (rationumaccumulationlist[i] +
                                   row) +
                                  globalconfig.MARK_X_OFFSET +
                                  block_x_offset, globalconfig.Y_BLANK +
                                  globalconfig.CUTLINE_Y_OFFSET +
                                  globalconfig.MARK_Y_OFFSET +
                                  block_y_offset])

        if globalconfig.BLOCK_X_NUM == 1 and globalconfig.BLOCK_Y_NUM == 1:
            mark = globalconfig.MARKNOTE + globalconfig.markratiolist[i]
        elif globalconfig.BLOCK_X_NUM == 1 or globalconfig.BLOCK_Y_NUM == 1:

            if globalconfig.BLOCK_Y_NUM == 1:
                if globalconfig.RATIO_NUM == 1:
                    mark = globalconfig.MARKNOTE + \
                        globalconfig.blockmark_x_list[block_x_count]
                else:
                    mark = globalconfig.MARKNOTE + \
                        globalconfig.blockmark_x_list[block_x_count] + globalconfig.markratiolist[i]
            if globalconfig.BLOCK_X_NUM == 1:
                if globalconfig.RATIO_NUM == 1:
                    mark = globalconfig.MARKNOTE + \
                        globalconfig.blockmark_y_list[block_y_count]
                else:
                    mark = globalconfig.MARKNOTE + \
                        globalconfig.blockmark_y_list[block_y_count] + globalconfig.markratiolist[i]
        else:
            if globalconfig.RATIO_NUM == 1:
                mark = globalconfig.MARKNOTE + \
                    globalconfig.blockmark_x_list[block_x_count] + globalconfig.blockmark_y_list[block_y_count]
            else:
                mark = globalconfig.MARKNOTE + \
                    globalconfig.blockmark_x_list[block_x_count] + globalconfig.blockmark_y_list[block_y_count] + globalconfig.markratiolist[i]
        markpointlistdict[mark] = markpointlist
    return markpointlistdict


def buildfilelist():
    """input nothing and return nothing
    """
    readfilelist = []
    dirdict = {}
    # writefilelist=[]
    mypath = os.path.dirname(sys.argv[0])
    mypath = os.path.abspath(mypath)
    os.chdir(mypath)

    for item in os.listdir(mypath):
        filepath = os.path.join(mypath, item)
        if os.path.isdir(filepath) and item.isdigit():
            readfilelist = []
            for onefile in os.listdir(filepath):
                filepath2 = os.path.join(filepath, onefile)
                if os.path.splitext(onefile)[
                        1] == '.dxf':  # 查找目录下的dxf文件，加入到readfilelist文件列表中
                    readfilelist.append(filepath2)
            # dirlist是字典，key是文件夹的名称，value是文件夹中dxf文件列表
            dirdict[int(item)] = readfilelist
    # feilin=file('feilin(ph).dxf','w')
    # #新建一个文件，名字先占位用，后续改成由配置文件中读入名称。

    return dirdict


def holepolylinedictarraycopy(holepolylinedict):
    """input a hole polyline dataset dict and array them by line
    """
    holepolylinearraydict = {}
    for e in holepolylinedict:  # 对通孔图层多段线字典进行遍历，将里面的多段线向上阵列
        holepolylinedataset = []
        for row in range(0, globalconfig.Y_ARRAY_NUM):
            holepolylinedataset.extend(
                datasetjustcopy(
                    holepolylinedict[e],
                    1,
                    1,
                    0,
                    globalconfig.Y_LENGTH /
                    globalconfig.Y_OUTLINE_RATIO *
                    row))
        holepolylinearraydict[e] = holepolylinedataset
    return holepolylinearraydict


# l-多段线列表  x_ratio-x方向放缩率 y_ratio-y方向放缩率 x_offset-x方向偏移 y_offset-y方向偏移
# layername-图层名称 arraycount-数数位置计数，判断是否在边缘？
def polylinedatasetarraycopy(
        l,
        x_ratio,
        y_ratio,
        x_offset,
        y_offset,
        layername,
        arraycount,
        arraylength,
        blockcount):
    """copy a polyline dataset and enlarged by a certain ratio
    """
    if layername in globalconfig.JUSTCOPYLIST and layername != "Outline":  # 根据图层名称判断是按中心放缩率直接放大后复制还是按多种放缩率放大后做边上的点的延伸或者不延伸的操作
        if arraycount == 0:
            dataset = datasetratiocopy_xl_extend(
                l,
                globalconfig.X_OUTLINE_RATIO,
                globalconfig.Y_OUTLINE_RATIO,
                x_offset,
                y_offset)
        elif arraycount == arraylength - 1:  # 判断是最右边的图案
            dataset = datasetratiocopy_xr_extend(
                l,
                globalconfig.X_OUTLINE_RATIO,
                globalconfig.Y_OUTLINE_RATIO,
                x_offset,
                y_offset)
        else:  # 判断是中间的图案
            dataset = datasetratiocopy_notextend(
                l,
                globalconfig.X_OUTLINE_RATIO,
                globalconfig.Y_OUTLINE_RATIO,
                x_offset,
                y_offset)
    elif layername == "Outline":
        dataset = datasetjustcopy(
            l,
            globalconfig.X_OUTLINE_RATIO,
            globalconfig.Y_OUTLINE_RATIO,
            x_offset,
            y_offset)
    elif layername in globalconfig.EXTENDCOPYLIST[blockcount]:
        dataset = datasetratiocopy_extend(
            l, x_ratio, y_ratio, x_offset, y_offset)
    else:
        if arraycount == 0:  # 判断是最左边的图案
            dataset = datasetratiocopy_xl_extend(
                l, x_ratio, y_ratio, x_offset, y_offset)
        elif arraycount == arraylength - 1:  # 判断是最右边的图案
            dataset = datasetratiocopy_xr_extend(
                l, x_ratio, y_ratio, x_offset, y_offset)
        else:  # 判断是中间的图案
            dataset = datasetratiocopy_notextend(
                l, x_ratio, y_ratio, x_offset, y_offset)
    return dataset


# l-多段线列表  ratio-放缩比例，基点是原点 x_offset y_offset-移动的偏移
def datasetjustcopy(l, x_ratio, y_ratio, x_offset, y_offset):
    """just enlarged by center ratio
    """
    dataset = []
    for polyline in l:
        newpolyline = []
        for pos in polyline:
            newpolyline.append(
                [pos[0] / x_ratio + x_offset, pos[1] / y_ratio + y_offset])
        dataset.append(newpolyline)
    return dataset


def datasetratiocopy_xl_extend(l, x_ratio, y_ratio, x_offset, y_offset):  # 只延伸上下两边以及左边的点
    """just enlarged a dataset by certain ratio with vertex on outline extended
    """
    dataset = []
    for polyline in l:
        newpolyline = []
        for pos in polyline:
            pos_x = pos[0]
            pos_y = pos[1]
            if abs((abs(pos_x) - globalconfig.X_LENGTH / 2)) < 0.01:
                if pos_x < 0:  # judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline and plus an extene length
                    pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + \
                        (abs(pos_x) / pos_x * globalconfig.X_EXTENDED_LENGTH) + x_offset
                else:
                    pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + x_offset
            else:
                pos_x = pos[0] / x_ratio + x_offset
            if abs((abs(pos_y) - globalconfig.Y_LENGTH / 2)) < 0.01:
                pos_y = pos[1] / globalconfig.Y_OUTLINE_RATIO + \
                    (abs(pos_y) / pos_y * globalconfig.Y_EXTENDED_LENGTH) + y_offset
            else:
                pos_y = pos[1] / y_ratio + y_offset
            newpolyline.append([pos_x, pos_y])
        dataset.append(newpolyline)
    return dataset


def datasetratiocopy_xr_extend(l, x_ratio, y_ratio, x_offset, y_offset):  # 只延伸上下两边以及右边的点
    """just enlarged a dataset by certain ratio with vertex on outline extended
    """
    dataset = []
    for polyline in l:
        newpolyline = []
        for pos in polyline:
            pos_x = pos[0]
            pos_y = pos[1]
            if abs((abs(pos_x) - globalconfig.X_LENGTH / 2)) < 0.01:
                if pos_x > 0:  # judge if the pos is on the origin outline,if on outline,will be moved to the new enlarged outline and plus an extene length
                    pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + \
                        (abs(pos_x) / pos_x * globalconfig.X_EXTENDED_LENGTH) + x_offset
                else:
                    pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + x_offset
            else:
                pos_x = pos[0] / x_ratio + x_offset
            if abs((abs(pos_y) - globalconfig.Y_LENGTH / 2)) < 0.01:
                pos_y = pos[1] / globalconfig.Y_OUTLINE_RATIO + \
                    (abs(pos_y) / pos_y * globalconfig.Y_EXTENDED_LENGTH) + y_offset
            else:
                pos_y = pos[1] / y_ratio + y_offset
            newpolyline.append([pos_x, pos_y])
        dataset.append(newpolyline)
    return dataset


def datasetratiocopy_extend(l, x_ratio, y_ratio, x_offset, y_offset):  # 全部四边上的点都延伸
    """just enlarged a dataset by certain ratio with vertex on outline extended
    """
    dataset = []
    for polyline in l:
        newpolyline = []
        for pos in polyline:
            pos_x = pos[0]
            pos_y = pos[1]
            # judge if the pos is on the origin outline,if on outline,will be
            # moved to the new enlarged outline and plus an extene length
            if abs((abs(pos_x) - globalconfig.X_LENGTH / 2)) < 0.01:
                pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + \
                    (abs(pos_x) / pos_x * globalconfig.X_EXTENDED_LENGTH) + x_offset
            else:
                pos_x = pos[0] / x_ratio + x_offset
            if abs((abs(pos_y) - globalconfig.Y_LENGTH / 2)) < 0.01:
                pos_y = pos[1] / globalconfig.Y_OUTLINE_RATIO + \
                    (abs(pos_y) / pos_y * globalconfig.Y_EXTENDED_LENGTH) + y_offset
            else:
                pos_y = pos[1] / y_ratio + y_offset
            newpolyline.append([pos_x, pos_y])
        dataset.append(newpolyline)
    return dataset


# 虽然说是不延伸，但是上下两边上的点Y方向还是会延伸的。
def datasetratiocopy_notextend(l, x_ratio, y_ratio, x_offset, y_offset):
    """just enlarged a dataset by certain ratio with vertex on outline not extended
    """
    dataset = []
    for polyline in l:
        newpolyline = []
        for pos in polyline:
            pos_x = pos[0]
            pos_y = pos[1]
            # judge if the pos is on the origin outline,if on outline,will be
            # moved to the new enlarged outline and plus an extene length
            if abs((abs(pos_x) - globalconfig.X_LENGTH / 2)) < 0.01:
                pos_x = pos[0] / globalconfig.X_OUTLINE_RATIO + x_offset
            else:
                pos_x = pos[0] / x_ratio + x_offset
            if abs((abs(pos_y) - globalconfig.Y_LENGTH / 2)) < 0.01:
                pos_y = pos[1] / globalconfig.Y_OUTLINE_RATIO + y_offset + (
                    abs(pos_y) / pos_y * globalconfig.Y_EXTENDED_LENGTH)  # 虽然说是不延伸，但是上下两边上的点Y方向还是会延伸的。
            else:
                pos_y = pos[1] / y_ratio + y_offset
            newpolyline.append([pos_x, pos_y])
        dataset.append(newpolyline)

    return dataset


# 1) Private (only for developpers)
_HEADER_POINTS = ['insbase', 'extmin', 'extmax']
# ---helper functions


def _point(x, index=0):
    """Convert tuple to a dxf point"""
    return '\n'.join(['%s\n%s' % ((i + 1) * 10 + index, x[i])
                      for i in range(len(x))])


def _points(p):
    """Convert a list of tuples to dxf points"""
    return [_point(p[i], i)for i in range(len(p))]

# ---base classes


class _Call:
    """Makes a callable class."""

    def copy(self):
        """Returns a copy."""
        return copy.deepcopy(self)

    def __call__(self, **attrs):
        """Returns a copy with modified attributes."""
        copied = self.copy()
        for attr in attrs:
            setattr(copied, attr, attrs[attr])
        return copied


class _Entity(_Call):
    """Base class for _common group codes for entities."""

    def __init__(self, color=None, extrusion=None, layer='0',
                 lineType=None, lineTypeScale=None, lineWeight=None,
                 thickness=None, parent=None):
        """None values will be omitted."""
        self.color = color
        self.extrusion = extrusion
        self.layer = layer
        self.lineType = lineType
        self.lineTypeScale = lineTypeScale
        self.lineWeight = lineWeight
        self.thickness = thickness
        self.parent = parent

    def _common(self):
        """Return common group codes as a string."""
        if self.parent:
            parent = self.parent
        else:
            parent = self
        result = '8\n%s' % parent.layer
        if parent.color is not None:
            result += '\n62\n%s' % parent.color
        if parent.extrusion is not None:
            result += '\n%s' % _point(parent.extrusion, 200)
        if parent.lineType is not None:
            result += '\n6\n%s' % parent.lineType
        if parent.lineWeight is not None:
            result += '\n370\n%s' % parent.lineWeight
        if parent.lineTypeScale is not None:
            result += '\n48\n%s' % parent.lineTypeScale
        if parent.thickness is not None:
            result += '\n39\n%s' % parent.thickness
        return result


class _Entities:
    """Base class to deal with composed objects."""

    def __dxf__(self):
        return []

    def __str__(self):
        return '\n'.join([str(x) for x in self.__dxf__()])


class _Collection(_Call):
    """Base class to expose entities methods to main object."""

    def __init__(self, entities=[]):
        self.entities = copy.copy(entities)
        # link entities methods to drawing
        for attr in dir(self.entities):
            if attr[0] != '_':
                attrObject = getattr(self.entities, attr)
                if callable(attrObject):
                    setattr(self, attr, attrObject)


# 2) Constants
# ---color values
BYBLOCK = 0
BYLAYER = 256

# ---block-type flags (bit coded values, may be combined):
ANONYMOUS = 1  # This is an anonymous block generated by hatching, associative dimensioning, other internal operations, or an application
# This block has non-constant attribute definitions (this bit is not set
# if the block has any attribute definitions that are constant, or has no
# attribute definitions at all)
NON_CONSTANT_ATTRIBUTES = 2
XREF = 4  # This block is an external reference (xref)
XREF_OVERLAY = 8  # This block is an xref overlay
EXTERNAL = 16  # This block is externally dependent
# This is a resolved external reference, or dependent of an external
# reference (ignored on input)
RESOLVED = 32
# This definition is a referenced external reference (ignored on input)
REFERENCED = 64

# ---mtext flags
# attachment point
TOP_LEFT = 1
TOP_CENTER = 2
TOP_RIGHT = 3
MIDDLE_LEFT = 4
MIDDLE_CENTER = 5
MIDDLE_RIGHT = 6
BOTTOM_LEFT = 7
BOTTOM_CENTER = 8
BOTTOM_RIGHT = 9
# drawing direction
LEFT_RIGHT = 1
TOP_BOTTOM = 3
BY_STYLE = 5  # the flow direction is inherited from the associated text style
# line spacing style (optional):
AT_LEAST = 1  # taller characters will override
EXACT = 2  # taller characters will not override

# ---polyline flags
# This is a closed polyline (or a polygon mesh closed in the M direction)
CLOSED = 1
CURVE_FIT = 2      # Curve-fit vertices have been added
SPLINE_FIT = 4      # Spline-fit vertices have been added
POLYLINE_3D = 8      # This is a 3D polyline
POLYGON_MESH = 16     # This is a 3D polygon mesh
CLOSED_N = 32     # The polygon mesh is closed in the N direction
POLYFACE_MESH = 64     # The polyline is a polyface mesh
# The linetype pattern is generated continuously around the vertices of
# this polyline
CONTINOUS_LINETYPE_PATTERN = 128

# ---text flags
# horizontal
LEFT = 0
CENTER = 1
RIGHT = 2
ALIGNED = 3  # if vertical alignment = 0
MIDDLE = 4  # if vertical alignment = 0
FIT = 5  # if vertical alignment = 0
# vertical
BASELINE = 0
BOTTOM = 1
MIDDLE = 2
TOP = 3

# 3) Classes
# ---entitities


class Arc(_Entity):
    """Arc, angles in degrees."""

    def __init__(self, center=(0, 0, 0), radius=1,
                 startAngle=0.0, endAngle=90, **common):
        """Angles in degrees."""
        _Entity.__init__(self, **common)
        self.center = center
        self.radius = radius
        self.startAngle = startAngle
        self.endAngle = endAngle

    def __str__(self):
        return '0\nARC\n%s\n%s\n40\n%s\n50\n%s\n51\n%s' %\
               (self._common(), _point(self.center),
                self.radius, self.startAngle, self.endAngle)


class Circle(_Entity):
    """Circle"""

    def __init__(self, center=(0, 0, 0), radius=1, **common):
        _Entity.__init__(self, **common)
        self.center = center
        self.radius = radius

    def __str__(self):
        return '0\nCIRCLE\n%s\n%s\n40\n%s' %\
               (self._common(), _point(self.center), self.radius)


class Face(_Entity):
    """3dface"""

    def __init__(self, points, **common):
        _Entity.__init__(self, **common)
        self.points = points

    def __str__(self):
        return '\n'.join(['0\n3DFACE', self._common()] +
                         _points(self.points)
                         )


class Insert(_Entity):
    """Block instance."""

    def __init__(self, name, point=(0, 0, 0),
                 xscale=None, yscale=None, zscale=None,
                 cols=None, colspacing=None, rows=None, rowspacing=None,
                 rotation=None,
                 **common):
        _Entity.__init__(self, **common)
        self.name = name
        self.point = point
        self.xscale = xscale
        self.yscale = yscale
        self.zscale = zscale
        self.cols = cols
        self.colspacing = colspacing
        self.rows = rows
        self.rowspacing = rowspacing
        self.rotation = rotation

    def __str__(self):
        result = '0\nINSERT\n2\n%s\n%s\n%s' %\
            (self.name, self._common(), _point(self.point))
        if self.xscale is not None:
            result += '\n41\n%s' % self.xscale
        if self.yscale is not None:
            result += '\n42\n%s' % self.yscale
        if self.zscale is not None:
            result += '\n43\n%s' % self.zscale
        if self.rotation:
            result += '\n50\n%s' % self.rotation
        if self.cols is not None:
            result += '\n70\n%s' % self.cols
        if self.colspacing is not None:
            result += '\n44\n%s' % self.colspacing
        if self.rows is not None:
            result += '\n71\n%s' % self.rows
        if self.rowspacing is not None:
            result += '\n45\n%s' % self.rowspacing
        return result


class Line(_Entity):
    """Line"""

    def __init__(self, points, **common):
        _Entity.__init__(self, **common)
        self.points = points

    def __str__(self):
        return '\n'.join(['0\nLINE', self._common()] +
                         _points(self.points))


class LwPolyLine(_Entity):
    """This is a LWPOLYLINE. I have no idea how it differs from a normal PolyLine"""

    def __init__(self, points, flag=0, width=None, **common):
        _Entity.__init__(self, **common)
        self.points = points
        self.flag = flag
        self.width = width

    def __str__(self):
        result = '0\nLWPOLYLINE\n%s\n70\n%s' %\
            (self._common(), self.flag)
        result += '\n90\n%s' % len(self.points)
        for point in self.points:
            result += '\n%s' % _point(point)
        if self.width:
            result += '\n40\n%s\n41\n%s' % (self.width, self.width)
        return result


class PolyPad(_Entity):
    # TODO: Finish polyline (now implemented as a series of lines)
    def __init__(self, points, layer='0', flag=0, width=None, **common):
        _Entity.__init__(self, **common)
        self.points = points
        self.flag = flag
        self.width = width
        self.layer = layer

    def __str__(self):
        result = '0\nPOLYLINE\n%s\n66\n%s\n70\n%s\n40\n%s\n41\n%s' %\
            (self._common(), self.flag, self.flag, self.width, self.width)
        for point in self.points:
            result += '\n0\nVERTEX\n8\n%s\n%s' % (self.layer, _point(point))
            if self.width:
                result += '\n42\n1.0'
        result += '\n0\nSEQEND'
        return result


class PolyLine(_Entity):
    # TODO: Finish polyline (now implemented as a series of lines)
    def __init__(self, points, layer='0', flag=0, width=None, **common):
        _Entity.__init__(self, **common)
        self.points = points
        self.flag = flag
        self.width = width
        self.layer = layer

    def __str__(self):
        result = '0\nPOLYLINE\n%s\n66\n%s\n70\n%s' %\
            (self._common(), self.flag, self.flag)
        for point in self.points:
            result += '\n0\nVERTEX\n8\n%s\n%s' % (self.layer, _point(point))
            if self.width:
                result += '\n40\n%s\n41\n%s' % (self.width, self.width)
        result += '\n0\nSEQEND'
        return result


class Point(_Entity):
    """Colored solid fill."""

    def __init__(self, points=None, **common):
        _Entity.__init__(self, **common)
        self.points = points


class SinglePoint(_Entity):
    """Colored solid fill."""

    def __init__(self, points, layer='0', **common):
        _Entity.__init__(self, **common)
        self.points = points
        self.layer = layer

    def __str__(self):
        result = ''
        for point in [self.points]:
            result += '0\nPOINT\n8\n%s\n%s' % (self.layer, _point(point))
        return result


class Solid(_Entity):
    """Colored solid fill."""

    def __init__(self, points=None, **common):
        _Entity.__init__(self, **common)
        self.points = points

    def __str__(self):
        return '\n'.join(['0\nSOLID', self._common()] +
                         _points(self.points[:2] +
                                 [self.points[3], self.points[2]]))


class Text(_Entity):
    """Single text line."""

    def __init__(
            self,
            text='',
            point=(
                0,
                0,
                0),
            alignment=None,
            flag=None,
            height=1,
            justifyhor=None,
            justifyver=None,
            rotation=None,
            obliqueAngle=None,
            style=None,
            xscale=None,
            **common):
        _Entity.__init__(self, **common)
        self.text = text
        self.point = point
        self.alignment = alignment
        self.flag = flag
        self.height = height
        self.justifyhor = justifyhor
        self.justifyver = justifyver
        self.rotation = rotation
        self.obliqueAngle = obliqueAngle
        self.style = style
        self.xscale = xscale

    def __str__(self):
        result = '0\nTEXT\n%s\n%s\n40\n%s\n1\n%s' %\
            (self._common(), _point(self.point), self.height, self.text)
        if self.rotation:
            result += '\n50\n%s' % self.rotation
        if self.xscale:
            result += '\n41\n%s' % self.xscale
        if self.obliqueAngle:
            result += '\n51\n%s' % self.obliqueAngle
        if self.style:
            result += '\n7\n%s' % self.style
        if self.flag:
            result += '\n71\n%s' % self.flag
        if self.justifyhor:
            result += '\n72\n%s' % self.justifyhor
        if self.alignment:
            result += '\n%s' % _point(self.alignment, 1)
        if self.justifyver:
            result += '\n73\n%s' % self.justifyver
        return result


class Mtext(Text):
    """Surrogate for mtext, generates some Text instances."""

    def __init__(
            self,
            text='',
            point=(
                0,
                0,
                0),
            width=250,
            spacingFactor=1.5,
            down=0,
            spacingWidth=None,
            **options):
        Text.__init__(self, text=text, point=point, **options)
        if down:
            spacingFactor *= -1
        self.spacingFactor = spacingFactor
        self.spacingWidth = spacingWidth
        self.width = width
        self.down = down

    def __str__(self):
        texts = self.text.replace('\r\n', '\n').split('\n')
        if not self.down:
            texts.reverse()
        result = ''
        x = y = 0
        if self.spacingWidth:
            spacingWidth = self.spacingWidth
        else:
            spacingWidth = self.height * self.spacingFactor
        for text in texts:
            while text:
                result += '\n%s' % Text(text[:self.width],
                                        point=(self.point[0] + x * spacingWidth,
                                               self.point[1] + y * spacingWidth,
                                               self.point[2]),
                                        alignment=self.alignment,
                                        flag=self.flag,
                                        height=self.height,
                                        justifyhor=self.justifyhor,
                                        justifyver=self.justifyver,
                                        rotation=self.rotation,
                                        obliqueAngle=self.obliqueAngle,
                                        style=self.style,
                                        xscale=self.xscale,
                                        parent=self)
                text = text[self.width:]
                if self.rotation:
                    x += 1
                else:
                    y += 1
        return result[1:]

# class _Mtext(_Entity):
##    """Mtext not functioning for minimal dxf."""
# def __init__(self,text='',point=(0,0,0),attachment=1,
# charWidth=None,charHeight=1,direction=1,height=100,rotation=0,
# spacingStyle=None,spacingFactor=None,style=None,width=100,
# xdirection=None,**common):
# _Entity.__init__(self,**common)
# self.text=text
# self.point=point
# self.attachment=attachment
# self.charWidth=charWidth
# self.charHeight=charHeight
# self.direction=direction
# self.height=height
# self.rotation=rotation
# self.spacingStyle=spacingStyle
# self.spacingFactor=spacingFactor
# self.style=style
# self.width=width
# self.xdirection=xdirection
# def __str__(self):
# input=self.text
# text=''
# while len(input)>250:
# text+='\n3\n%s'%input[:250]
# input=input[250:]
# text+='\n1\n%s'%input
# result= '0\nMTEXT\n%s\n%s\n40\n%s\n41\n%s\n71\n%s\n72\n%s%s\n43\n%s\n50\n%s'%\
# (self._common(),_point(self.point),self.charHeight,self.width,
# self.attachment,self.direction,text,
# self.height,
# self.rotation)
##        if self.style:result+='\n7\n%s'%self.style
##        if self.xdirection:result+='\n%s'%_point(self.xdirection,1)
##        if self.charWidth:result+='\n42\n%s'%self.charWidth
##        if self.spacingStyle:result+='\n73\n%s'%self.spacingStyle
##        if self.spacingFactor:result+='\n44\n%s'%self.spacingFactor
# return result

# ---tables


class Block(_Collection):
    """Use list methods to add entities, eg append."""

    def __init__(self, name, layer='0', flag=0, base=(0, 0, 0), entities=[]):
        self.entities = copy.copy(entities)
        _Collection.__init__(self, entities)
        self.layer = layer
        self.name = name
        self.flag = 0
        self.base = base

    def __str__(self):
        e = '\n'.join([str(x)for x in self.entities])
        return '0\nBLOCK\n8\n%s\n2\n%s\n70\n%s\n%s\n3\n%s\n%s\n0\nENDBLK' % (
            self.layer, self.name, self.flag, _point(self.base), self.name, e)


class Layer(_Call):
    """Layer"""

    def __init__(self, name='0', color=255, lineType='continuous', flag=0):
        self.name = name
        self.color = color
        self.lineType = lineType
        self.flag = flag

    def __str__(self):
        return '0\nLAYER\n2\n%s\n70\n%s\n62\n%s\n6\n%s' %\
               (self.name, self.flag, self.color, self.lineType)


class LineType(_Call):
    """Custom linetype"""

    def __init__(
            self,
            name='continuous',
            description='Solid line',
            elements=[],
            flag=64):
        # TODO: Implement lineType elements
        self.name = name
        self.description = description
        self.elements = copy.copy(elements)
        self.flag = flag

    def __str__(self):
        return '0\nLTYPE\n2\n%s\n70\n%s\n3\n%s\n72\n65\n73\n%s\n40\n0.0' % (
            self.name.upper(), self.flag, self.description, len(self.elements))


class Style(_Call):
    """Text style"""

    def __init__(
            self,
            name='standard',
            flag=0,
            height=0,
            widthFactor=1,
            obliqueAngle=0,
            mirror=0,
            lastHeight=1,
            font='arial.ttf',
            bigFont=''):
        self.name = name
        self.flag = flag
        self.height = height
        self.widthFactor = widthFactor
        self.obliqueAngle = obliqueAngle
        self.mirror = mirror
        self.lastHeight = lastHeight
        self.font = font
        self.bigFont = bigFont

    def __str__(self):
        return '0\nSTYLE\n2\n%s\n70\n%s\n40\n%s\n41\n%s\n50\n%s\n71\n%s\n42\n%s\n3\n%s\n4\n%s' %\
               (self.name.upper(), self.flag, self.flag, self.widthFactor,
                self.obliqueAngle, self.mirror, self.lastHeight,
                self.font.upper(), self.bigFont.upper())


class View(_Call):
    def __init__(self, name, flag=0, width=1, height=1, center=(0.5, 0.5),
                 direction=(0, 0, 1), target=(0, 0, 0), lens=50,
                 frontClipping=0, backClipping=0, twist=0, mode=0):
        self.name = name
        self.flag = flag
        self.width = width
        self.height = height
        self.center = center
        self.direction = direction
        self.target = target
        self.lens = lens
        self.frontClipping = frontClipping
        self.backClipping = backClipping
        self.twist = twist
        self.mode = mode

    def __str__(self):
        return '0\nVIEW\n2\n%s\n70\n%s\n40\n%s\n%s\n41\n%s\n%s\n%s\n42\n%s\n43\n%s\n44\n%s\n50\n%s\n71\n%s' %\
               (self.name, self.flag, self.height, _point(self.center), self.width,
                _point(self.direction, 1), _point(self.target, 2), self.lens,
                self.frontClipping, self.backClipping, self.twist, self.mode)


def ViewByWindow(name, leftBottom=(0, 0), rightTop=(1, 1), **options):
    width = abs(rightTop[0] - leftBottom[0])
    height = abs(rightTop[1] - leftBottom[1])
    center = ((rightTop[0] + leftBottom[0]) * 0.5,
              (rightTop[1] + leftBottom[1]) * 0.5)
    return View(
        name=name,
        width=width,
        height=height,
        center=center,
        **options)

# ---drawing


class Drawing(_Collection):
    """Dxf drawing. Use append or any other list methods to add objects."""

    def __init__(self, insbase=(0.0, 0.0, 0.0), extmin=(0.0, 0.0), extmax=(0.0, 0.0),
                 layers=[Layer()], linetypes=[LineType()], styles=[Style()], blocks=[],
                 views=[], entities=None, fileName='test.dxf'):
        # TODO: replace list with None,arial
        if not entities:
            entities = []
        _Collection.__init__(self, entities)
        self.insbase = insbase
        self.extmin = extmin
        self.extmax = extmax
        self.layers = copy.copy(layers)
        self.linetypes = copy.copy(linetypes)
        self.styles = copy.copy(styles)
        self.views = copy.copy(views)
        self.blocks = copy.copy(blocks)
        self.fileName = fileName
        # private
        self.acadver = '9\n$ACADVER\n1\nAC1006'

    def _name(self, x):
        """Helper function for self._point"""
        return '9\n$%s' % x.upper()

    def _point(self, name, x):
        """Point setting from drawing like extmin,extmax,..."""
        return '%s\n%s' % (self._name(name), _point(x))

    def _section(self, name, x):
        """Sections like tables,blocks,entities,..."""
        if x:
            xstr = '\n' + '\n'.join(x)
        else:
            xstr = ''
        return '0\nSECTION\n2\n%s%s\n0\nENDSEC' % (name.upper(), xstr)

    def _table(self, name, x):
        """Tables like ltype,layer,style,..."""
        if x:
            xstr = '\n' + '\n'.join(x)
        else:
            xstr = ''
        return '0\nTABLE\n2\n%s\n70\n%s%s\n0\nENDTAB' % (
            name.upper(), len(x), xstr)

    def __str__(self):
        """Returns drawing as dxf string."""
        header = [self.acadver] + \
            [self._point(attr, getattr(self, attr)) for attr in _HEADER_POINTS]
        header = self._section('header', header)

        tables = [self._table('ltype', [str(x) for x in self.linetypes]),
                  self._table('layer', [str(x) for x in self.layers]),
                  self._table('style', [str(x) for x in self.styles]),
                  self._table('view', [str(x) for x in self.views]),
                  ]
        tables = self._section('tables', tables)

        blocks = self._section('blocks', [str(x) for x in self.blocks])

        entities = self._section('entities', [str(x) for x in self.entities])

        all = '\n'.join([header, tables, blocks, entities, '0\nEOF\n'])
        return all

    def saveas(self, fileName):
        self.fileName = fileName
        self.save()

    def save(self):
        test = open(self.fileName, 'w')
        test.write(str(self))
        test.close()


# ---extras
class Rectangle(_Entity):
    """Rectangle, creates lines."""

    def __init__(
            self,
            point=(
                0,
                0,
                0),
            width=1,
            height=1,
            solid=None,
            line=1,
            **common):
        _Entity.__init__(self, **common)
        self.point = point
        self.width = width
        self.height = height
        self.solid = solid
        self.line = line

    def __str__(self):
        result = ''
        points = [
            self.point,
            (self.point[0] +
             self.width,
             self.point[1],
             self.point[2]),
            (self.point[0] +
             self.width,
             self.point[1] +
             self.height,
             self.point[2]),
            (self.point[0],
             self.point[1] +
             self.height,
             self.point[2]),
            self.point]
        if self.solid:
            result += '\n%s' % Solid(points=points[:-1], parent=self.solid)
        if self.line:
            for i in range(4):
                result += '\n%s' %\
                    Line(points=[points[i], points[i + 1]], parent=self)
        return result[1:]


class LineList(_Entity):
    """Like polyline, but built of individual lines."""

    def __init__(self, points=[], closed=0, **common):
        _Entity.__init__(self, **common)
        self.closed = closed
        self.points = copy.copy(points)

    def __str__(self):
        if self.closed:
            points = self.points + [self.points[0]]
        else:
            points = self.points
        result = ''
        for i in range(len(points) - 1):
            result += '\n%s' %\
                Line(points=[points[i], points[i + 1]], parent=self)
        return result[1:]


# ---test


def main():
    # Blocks
    # hole_list=[]
    # feilin_list=[]
    b = Block('cutlineendpoint')
    b.append(PolyPad(points=[(-0.02, 0, 0), (0.02, 0, 0)], flag=1, width=0.04))

    # Drawing
    feilin = Drawing()
    # tables
    feilin.blocks.append(b)  # table blocks
    feilin.styles.append(Style())  # table styles
    feilin.views.append(View('Normal'))  # table view
    # feilin.views.append(ViewByWindow('Window',leftBottom=(1,0),rightTop=(2,1)))
    # #idem

    # 绘制菲林内部图案
    dirdict = buildfilelist()
    blocknum = len(dirdict)

    # 一个初略的输入检查,若目录中的菲林目录数量与配置中给定的拼网行列数量对不上，则不运行程序，提示后直接退出
    if blocknum != globalconfig.BLOCK_Y_NUM * globalconfig.BLOCK_X_NUM:
        print("dict no. is not equal to config.ini setting!!!")
        return 0

    # 检查MARK大小
    # if globalconfig.MARK_HEIGHT<0.70:
       # print("MARK height is less than 0.70,plz adjust mark height!!!")
       # return 0

    blockseqlist = list(dirdict.keys())

    if len(blockseqlist) > 1:
        blockseqlist.sort()

    feilinhole = Feilinhole()

    feilin_dxfpolyline = Feilin_dxfpolyline(blocknum)

    for blockcount, blockname in enumerate(
            blockseqlist):  # blockcount-第几个区块？ blockname-区块名称，就是目录名
        # if globalconfig.holemaxdiameterlist[blockcount]>0.11:
        #    print("holemaxdiameter is larger then 0.11,there must be sth wrong!!!");
        #    return 0
        eachrationumlist, holepolylinedict, feilinpolylinedict = feilin_dxfpolyline.createnewblock(
            blockname, blockcount, dirdict[blockname])
        for feilinlayer in feilinpolylinedict:  # 遍历字典
            for polyline in feilinpolylinedict[feilinlayer]:  # 遍历字典值，即多段线列表
                feilin.append(
                    PolyLine(
                        points=polyline,
                        layer=feilinlayer,
                        flag=1))

        if globalconfig.DRAWHOLE:
            for holelayer in holepolylinedict:
                for polyline in holepolylinedict[holelayer]:
                    feilin.append(
                        PolyLine(
                            points=polyline,
                            layer=holelayer,
                            flag=1))

        if globalconfig.DRAWPAD:
            for holelayer in globalconfig.holepadpairdictlist[blockcount]:
                if holelayer in list(holepolylinedict.keys()):
                    if globalconfig.holepadpairdictlist[blockcount][holelayer] not in feilin_dxfpolyline.feilin_list:
                        feilin_dxfpolyline.feilin_list.append(
                            globalconfig.holepadpairdictlist[blockcount][holelayer])
                    for centerpos in feilinhole.calculateholecenterposlist(
                            holepolylinedict[holelayer]):
                        feilin.append(
                            Circle(
                                center=centerpos,
                                radius=globalconfig.PADDIAMETER / 2,
                                layer=globalconfig.holepadpairdictlist[blockcount][holelayer]))

        # 绘制菲林MARK
        markpointlistdict = buildmarkpointlist(eachrationumlist, blockcount)
        if globalconfig.DRAWMARKNOTE:
            for mark in markpointlistdict:
                for markpoint in markpointlistdict[mark]:
                    feilin.append(
                        Text(
                            layer='Mark',
                            text=mark,
                            point=markpoint,
                            height=globalconfig.MARK_HEIGHT,
                            rotation=globalconfig.MARK_ROTATION_ANGLE))
        # 统计通孔坐标
        feilinhole.appendnewblockholedict(holepolylinedict, blockcount)

        # 绘制图层通孔对应的多段线
        layerholedxf = Drawing()
        layerholepairlist, notepointdict = feilin_dxfpolyline.createlayerholepair(
            blockname, blockcount, dirdict[blockname])

        layercolordict = {}
        for layername in layerholepairlist:
            t = random.randint(10, 17)
            layercolordict[layername] = random.randrange(10 + t, 240 + t, 10)

        layercolordict["Outline"] = 1
        layercolordict["Mark"] = 5

        for e in layerholepairlist:
            layerholedxf.layers.append(Layer(name=e, color=layercolordict[e]))
            for polyline in layerholepairlist[e]:
                layerholedxf.append(PolyLine(points=polyline, layer=e, flag=1))

        # 绘制图层通孔对应的图层名称对应关系
        for note in notepointdict:
            layerholedxf.append(
                Text(
                    layer='0',
                    text=note,
                    point=notepointdict[note],
                    height=0.25 *
                    globalconfig.Y_LENGTH,
                    rotation=0))
        layerholedxf.saveas(str(blockname) + '.dxf')

    # 给菲林图层上色
    layercolordict = {}
    for layername in feilin_dxfpolyline.feilin_list:
        t = random.randint(10, 17)
        layercolordict[layername] = random.randrange(10 + t, 240 + t, 10)

    layercolordict["Outline"] = 1
    layercolordict["Mark"] = 5
    # layercolordict["Cutline"]=2

    for e in layercolordict:
        feilin.layers.append(Layer(name=e, color=layercolordict[e]))

#    for holelayer in holepolylinedict:
#        if holelayer in globalconfig.LONGHOLELIST:
#            longholedxf=Drawing()
#            longholedxf.blocks.append(b)
#            for centerpos in feilinhole.calculaterlongholecenterposlist(holelayer):
#                longholedxf.append(Circle(center=centerpos,radius=globalconfig.LONGHOLEDIAMETER/2,layer=holelayer))
#            for ring in buildringlist():
#                longholedxf.append(PolyPad(points=ring,layer=holelayer,flag=1,width=globalconfig.RING_WIDTH))
#            #for cutline in buildcutlineset():
#                #longholedxf.append(PolyLine(points=cutline,layer=holelayer,flag=1,width=globalconfig.CUTLINE_WIDTH))
#            #for flash in buildflashlist():
#                #longholedxf.append(Insert(layer=holelayer,name='cutlineendpoint',point=flash))
#            longholedxf.saveas(holelayer+u'(长通孔)'+'.dxf')

    # 绘制长通孔层
    if globalconfig.DRAWLONGHOLE:
        longholedxf = Drawing()
        longholedxf.blocks.append(b)
        for holelayer in holepolylinedict:
            if holelayer in globalconfig.LONGHOLELIST:
                for centerpos in feilinhole.calculaterlongholecenterposlist(
                        holelayer):
                    longholedxf.append(
                        Circle(
                            center=centerpos,
                            radius=globalconfig.LONGHOLEDIAMETER / 2,
                            layer=holelayer))
                for ring in buildringlist():
                    longholedxf.append(
                        PolyPad(
                            points=ring,
                            layer=holelayer,
                            flag=1,
                            width=globalconfig.RING_WIDTH))
                # for cutline in buildcutlineset():
                    # longholedxf.append(PolyLine(points=cutline,layer=holelayer,flag=1,width=globalconfig.CUTLINE_WIDTH))
                # for flash in buildflashlist():
                    # longholedxf.append(Insert(layer=holelayer,name='cutlineendpoint',point=flash))
        longholedxf.saveas(globalconfig.NAME_OF_FEILIN + '(长通孔)' + '.dxf')

    # 绘制盛雄开孔机用的菲林
    for holelayer in holepolylinedict:
        shengxiongholedxf = Drawing()
        shengxiongholedxf.blocks.append(b)
        for centerpos in feilinhole.calculaterlongholecenterposlist(holelayer):
            if globalconfig.HOLEDIAMETER <= 0.0425:
                shengxiongholedxf.append(
                    SinglePoint(
                        points=centerpos,
                        layer=holelayer))
            elif globalconfig.HOLEDIAMETER >= 0.0425 and globalconfig.HOLEDIAMETER <= 0.0595:
                shengxiongholedxf.append(
                    Circle(
                        center=centerpos,
                        radius=0.0175,
                        layer=holelayer))
                shengxiongholedxf.append(
                    SinglePoint(
                        points=centerpos,
                        layer='PET'))
            elif globalconfig.HOLEDIAMETER >= 0.0595 and globalconfig.HOLEDIAMETER <= 0.0765:
                shengxiongholedxf.append(
                    Circle(
                        center=centerpos,
                        radius=0.0275,
                        layer=holelayer))
                shengxiongholedxf.append(
                    SinglePoint(
                        points=centerpos,
                        layer='PET'))
            elif globalconfig.HOLEDIAMETER >= 0.0765 and globalconfig.HOLEDIAMETER <= 0.0935:
                shengxiongholedxf.append(
                    Circle(
                        center=centerpos,
                        radius=0.0375,
                        layer=holelayer))
                shengxiongholedxf.append(
                    SinglePoint(
                        points=centerpos,
                        layer='PET'))
            elif globalconfig.HOLEDIAMETER >= 0.0935 and globalconfig.HOLEDIAMETER <= 0.102:
                shengxiongholedxf.append(
                    Circle(
                        center=centerpos,
                        radius=0.0475,
                        layer=holelayer))
                shengxiongholedxf.append(
                    SinglePoint(
                        points=centerpos,
                        layer='PET'))
            elif globalconfig.HOLEDIAMETER >= 0.102 and globalconfig.HOLEDIAMETER <= 0.119:
                shengxiongholedxf.append(
                    Circle(
                        center=centerpos,
                        radius=0.055,
                        layer=holelayer))
                shengxiongholedxf.append(
                    SinglePoint(
                        points=centerpos,
                        layer='PET'))
            elif globalconfig.HOLEDIAMETER >= 0.119 and globalconfig.HOLEDIAMETER <= 0.1445:
                shengxiongholedxf.append(
                    Circle(
                        center=centerpos,
                        radius=0.065,
                        layer=holelayer))
                shengxiongholedxf.append(
                    SinglePoint(
                        points=centerpos,
                        layer='PET'))
            elif globalconfig.HOLEDIAMETER >= 0.1445:
                shengxiongholedxf.append(
                    Circle(
                        center=centerpos,
                        radius=globalconfig.HOLEDIAMETER /
                        1.7 -
                        0.01,
                        layer=holelayer))
                shengxiongholedxf.append(
                    SinglePoint(
                        points=centerpos,
                        layer='PET'))
        for ring in buildringholelist():
            shengxiongholedxf.append(
                Circle(
                    center=ring,
                    radius=globalconfig.RING_RADIUS / 2,
                    layer='0'))
        shengxiongholedxf.saveas(
            globalconfig.NAME_OF_FEILIN +
            '-' +
            holelayer +
            '(盛雄开孔模式)' +
            '.dxf')

    # 绘制切割线,菲林名称,定位圆环,十字架
    for feilin_layer in feilin_dxfpolyline.feilin_list:
        for ring in buildringlist():
            feilin.append(
                PolyPad(
                    points=ring,
                    layer=feilin_layer,
                    flag=1,
                    width=globalconfig.RING_WIDTH))
        for cutline in buildcutlineset():
            feilin.append(
                PolyLine(
                    points=cutline,
                    layer=feilin_layer,
                    flag=1,
                    width=globalconfig.CUTLINE_WIDTH))
        for flash in buildflashlist():
            feilin.append(
                Insert(
                    layer=feilin_layer,
                    name='cutlineendpoint',
                    point=flash))
        if feilin_layer.capitalize()[0] == 'P' or feilin_layer.capitalize()[
                0] == 'H':
            Title_height_offset = 5.5
        else:
            Title_height_offset = 8.5
        feilin.append(
            Text(
                layer=feilin_layer,
                text=globalconfig.NAME_OF_FEILIN +
                '-' +
                feilin_layer,
                point=(
                    globalconfig.RING_DISTANCE /
                    2 -
                    len(
                        globalconfig.NAME_OF_FEILIN) *
                    1.5 /
                    2 +
                    globalconfig.CUTLINE_X_OFFSET,
                    Title_height_offset +
                    globalconfig.RING_DISTANCE +
                    globalconfig.CUTLINE_Y_OFFSET),
                height=1.5))
        feilin.append(
            Text(
                layer=feilin_layer,
                text='Date:' +
                time.strftime(
                    '%Y-%m-%d',
                    time.localtime(
                        time.time())) +
                '    设计者:' +
                globalconfig.AUTHOR_NAME,
                point=(
                    globalconfig.RING_DISTANCE /
                    2 -
                    25.0 +
                    globalconfig.CUTLINE_X_OFFSET,
                    globalconfig.CUTLINE_Y_OFFSET +
                    globalconfig.RING_DISTANCE /
                    2 -
                    122 -
                    1.5),
                height=1.5))
    feilinnote = "说明:需要制作菲林的图层为"
    for f in feilin_dxfpolyline.feilin_list:
        feilinnote = feilinnote + f + '  '
    # info.write("\n阵列方式:请将以上图层图案向上阵列"+str(globalconfig.Y_ARRAY_NUM)+"行，行偏移为"+'{:.4f}'.format(round(globalconfig.Y_LENGTH/globalconfig.Y_OUTLINE_RATIO,4))+"mm\n")
    feilinnote = feilinnote + "\n阵列方式:请将以上图层图案\n"
    for line in range(0, globalconfig.BLOCK_Y_NUM):
        feilinnote = feilinnote + "从下至上数，位于第" + str(
            line + 1) + "行outline框中的图案向上阵列" + str(
            globalconfig.eachblock_y_list[line]) + "行，行偏移为" + '{:.4f}'.format(
            round(
                globalconfig.Y_LENGTH / globalconfig.Y_OUTLINE_RATIO,
                4)) + "mm\n"
        if feilin_dxfpolyline.blocknum > 1:
            feilinnote = feilinnote + "有部分的图层图案未分布在每一行，故阵列后这些图层的图案不会布满菲林图案区域，此外正常设计，请注意\n"
    feilin.append(
        Mtext(
            layer='0',
            text=feilinnote,
            point=(
                globalconfig.RING_DISTANCE *
                1.5 +
                globalconfig.CUTLINE_X_OFFSET,
                globalconfig.CUTLINE_Y_OFFSET +
                globalconfig.RING_DISTANCE /
                2,
                0),
            height=1.5))

    # 绘制所有菲林图案
    feilin.saveas(globalconfig.NAME_OF_FEILIN + '(总菲林)' + '.dxf')
    # 输出菲林信息文件
    feilin_dxfpolyline.outputfeilininfo()
    # 输出菲林通孔坐标文件
    feilinhole.outputholepos()
    # 输出长通孔坐标文件
    if globalconfig.DRAWLONGHOLE:
        feilinhole.outputlongholepos()


if __name__ == '__main__':
    globalconfig = Globalconfig()
    main()
