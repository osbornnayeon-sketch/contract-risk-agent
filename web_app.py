from __future__ import annotations

import hashlib
import html
import hmac
import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import parse_qs, urlparse

from legal_kb_client import LegalKnowledgeBaseClient


HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 8765))
OFFICIAL_CASE_LIBRARY_URL = "http://rmfyalk.court.gov.cn"
CASE_LIBRARY_PATH = Path(__file__).with_name("cases.json")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
AUTH_COOKIE_NAME = "case_agent_auth"


# 法律知识库 API 配置：
# 1. 没有配置 LEGAL_KB_API_URL 时，系统只使用本地 cases.json / 内置案例。
# 2. 配置 LEGAL_KB_API_URL 后，/api/search 会自动把案情解析结果发送给授权法律知识库。
# 3. 如需鉴权，可配置 LEGAL_KB_API_KEY；默认以 Bearer Token 形式放入 Authorization。
# 4. 如数据库要求自定义 Header，可用 LEGAL_KB_API_KEY_HEADER 指定，例如 X-API-Key。
# 5. 本地调试没有真实 API 时，可配置 LEGAL_KB_MOCK_FILE 指向一个 JSON 文件模拟返回。
LEGAL_KB_API_URL = os.environ.get("LEGAL_KB_API_URL", "").strip()
LEGAL_KB_API_KEY = os.environ.get("LEGAL_KB_API_KEY", "").strip()
LEGAL_KB_API_KEY_HEADER = os.environ.get("LEGAL_KB_API_KEY_HEADER", "Authorization").strip() or "Authorization"
LEGAL_KB_TIMEOUT = float(os.environ.get("LEGAL_KB_TIMEOUT", "12"))
LEGAL_KB_TOP_K = int(os.environ.get("LEGAL_KB_TOP_K", "10"))
LEGAL_KB_MOCK_FILE = os.environ.get("LEGAL_KB_MOCK_FILE", "").strip()
LEGAL_KB_CLIENT = LegalKnowledgeBaseClient()


LEGAL_KEYWORDS = {
    "直播带货": ["直播", "带货", "主播", "达人", "直播间", "短视频"],
    "虚假宣传": ["虚假宣传", "夸大宣传", "误导", "不实", "绝对化用语", "功效宣传"],
    "消费者权益": ["消费者", "购买", "退货", "欺诈", "三倍赔偿"],
    "产品责任": ["质量问题", "缺陷", "食品安全", "药品", "保健品", "瑕疵"],
    "网络平台责任": ["平台", "电商平台", "审核", "下架", "店铺", "入驻"],
    "广告代言": ["代言", "推荐", "证明", "广告", "背书"],
    "合同纠纷": ["合同", "订单", "价款", "违约", "退款"],
    "侵权责任": ["侵权", "损害", "损失", "过错", "因果关系"],
    "连带责任": ["连带责任", "共同责任", "共同侵权", "补充责任"],
    "明知应知": ["明知", "应知", "未核实", "审查义务", "注意义务"],
    "获利分成": ["佣金", "分成", "收益", "坑位费", "推广费", "返佣"],
    "网约车服务": ["网约车", "司机", "乘客", "接单", "派单", "行程", "平台派单"],
    "绕路": ["绕路", "偏航", "路线", "导航", "未按约定路线", "延误"],
    "误机损失": ["误机", "航班", "机票", "退改签", "赶飞机", "行程延误"],
    "运输合同": ["运输合同", "客运合同", "旅客运输", "承运人", "安全送达"],
    "违约赔偿": ["违约赔偿", "可预见损失", "扩大损失", "损失证明"],
    "健身服务": ["健身房", "健身馆", "私教", "健身服务", "会籍", "健身会员"],
    "预付卡": ["会员卡", "储值卡", "预付卡", "充值", "余额", "剩余课时", "预付款"],
    "闭店停业": ["闭店", "跑路", "停业", "关店", "歇业", "无法履约", "门店关闭"],
    "余额返还": ["追回", "退费", "退款", "返还", "余额返还", "解除合同"],
    "餐饮服务": ["餐厅", "饭店", "酒店", "餐饮", "包间", "宴席", "用餐", "就餐"],
    "禁止自带酒水": ["禁止自带酒水", "自带酒水", "不得自带酒水", "谢绝自带酒水", "开瓶费", "酒水服务费"],
    "格式条款": ["格式条款", "霸王条款", "店堂告示", "单方规定", "消费者选择权", "公平交易权"],
    "外卖配送": ["外卖", "骑手", "送餐", "配送", "配送员", "众包", "专送", "即时配送"],
    "交通事故": ["撞伤", "撞倒", "刮碰", "行人", "交通事故", "电动车", "非机动车", "机动车"],
    "道路交通事故": ["驾车", "开车", "斑马线", "人行横道", "交警", "事故认定书", "司机撞人"],
    "人身损害赔偿": ["医疗费", "误工费", "护理费", "残疾赔偿金", "住院", "伤残", "精神损害抚慰金"],
    "行人过错": ["看手机", "闯红灯", "未注意观察", "行人过错", "减轻责任", "责任分担"],
    "相邻关系": ["邻居", "相邻", "楼上", "楼下", "隔壁", "业主", "小区", "物业"],
    "空调外机侵扰": ["空调外机", "外机位", "噪声", "噪音", "震动", "振动", "滴水", "夜间休息"],
    "工业品买卖": ["芯片", "元器件", "零部件", "工业品", "采购", "供货", "交货", "供应商"],
    "质量异议": ["质量问题", "性能不达标", "不合格", "质量异议", "检测报告", "检验报告", "验收"],
    "货款支付": ["货款", "尾款", "拒付", "付款", "逾期利息", "应付账款"],
    "下游损失": ["下游客户", "退货损失", "停产损失", "替换成本", "召回", "间接损失"],
    "商铺租赁": ["商铺", "店铺租赁", "门面", "门面房", "商业用房", "商场铺位", "经营场所"],
    "租金违约": ["欠租", "拖欠租金", "降租", "减租", "租金调整", "自行搬离", "腾退"],
    "情势变更": ["情势变更", "疫情", "商圈人流", "客流量", "经营困难", "重大变化"],
    "股东知情权": ["股东知情权", "查阅会计账簿", "会计账簿", "原始凭证", "查账", "关联交易", "大股东"],
    "不正当目的": ["目的不正当", "竞争企业", "同业竞争", "商业秘密", "损害公司利益"],
    "网络购物": ["网购", "网络购物", "卖家", "店铺", "旗舰店", "商品页面", "电商平台", "收货"],
    "商品真伪": ["假货", "仿品", "正品", "官方正品", "假一赔三", "支持鉴定", "限量版", "运动鞋", "IMEI", "序列号", "无法激活", "串货", "翻新机"],
    "惩罚性赔偿": ["三倍赔偿", "退一赔三", "欺诈", "鉴定", "拆封"],
    "平台责任": ["平台免责", "提供卖家信息", "投诉记录", "多次投诉", "知道或应当知道", "下架", "审核"],
    "离婚房产执行": ["离婚协议", "协议离婚", "离婚财产", "未办理过户", "执行异议", "解除查封"],
    "夫妻债务": ["共同债务", "个人债务", "婚前债务", "婚后债务", "经营所欠"],
    "物业公共收益": ["业委会", "物业公司", "公共收益", "广告位", "电梯广告", "公共区域", "公布账目"],
    "收益返还": ["返还收益", "公示收益", "分配收益", "维修支出", "合理成本"],
    "平台用工": ["平台用工", "算法派单", "劳动关系", "劳务关系", "承揽", "雇佣", "管理控制"],
    "用人单位责任": ["用人单位责任", "雇主责任", "工作人员侵权", "执行工作任务", "职务行为", "替代责任"],
    "宠物寄养": ["宠物", "宠物店", "寄养", "托管", "看护", "猫", "狗", "走失"],
    "民间借贷": ["民间借贷", "借款", "借钱", "欠款", "借条", "欠条", "出借", "贷款"],
    "借款利息": ["利息", "利率", "高利息", "高利贷", "月息", "年息", "复利", "砍头息"],
    "本息返还": ["本金", "还本付息", "本息", "还款", "逾期利息", "违约金"],
}


ISSUE_TEMPLATES = [
    ("是否构成虚假宣传", ["虚假宣传", "夸大宣传", "不实", "误导", "绝对化用语", "功效宣传"]),
    ("主播是否参与商品宣传并形成交易影响", ["主播", "直播", "带货", "推荐", "证明", "背书"]),
    ("主播是否明知或应知宣传内容不实", ["明知", "应知", "未核实", "审查义务", "注意义务"]),
    ("主播、商家、平台之间如何分配责任", ["连带责任", "平台", "商家", "责任分配", "共同侵权"]),
    ("消费者是否因宣传产生错误认识并购买", ["消费者", "购买", "误导", "错误认识", "因果关系"]),
    ("主播获利或合作模式是否影响责任认定", ["佣金", "分成", "合作", "坑位费", "推广费"]),
    ("平台是否尽到审核、提示和处置义务", ["平台", "审核", "下架", "入驻", "投诉"]),
    ("网约车司机绕路或延误是否构成违约", ["网约车", "司机", "绕路", "偏航", "延误"]),
    ("误机损失是否属于可预见且可证明的赔偿范围", ["误机", "航班", "机票", "退改签", "可预见损失"]),
    ("网约车平台是否应对司机履约行为承担责任", ["平台", "派单", "网约车", "运输合同", "承运人"]),
    ("健身房闭店是否构成根本违约", ["健身房", "闭店", "停业", "无法履约", "关店"]),
    ("会员卡余额或剩余课时能否返还", ["会员卡", "预付卡", "余额", "剩余课时", "退费", "返还"]),
    ("经营者转让门店或变更主体后谁承担退款责任", ["转让", "更名", "新经营者", "原经营者", "承接"]),
    ("格式条款或不退费约定是否有效", ["格式条款", "不退费", "霸王条款", "单方解释", "消费者"]),
    ("餐厅禁止自带酒水是否构成不公平格式条款", ["禁止自带酒水", "自带酒水", "格式条款", "霸王条款", "餐厅"]),
    ("餐饮经营者能否收取开瓶费或酒水服务费", ["开瓶费", "酒水服务费", "餐饮", "服务费"]),
    ("店堂告示是否已经合理提示且是否排除消费者主要权利", ["店堂告示", "合理提示", "消费者选择权", "公平交易权"]),
    ("骑手送餐途中撞伤行人是否属于执行工作任务", ["外卖", "骑手", "送餐", "撞伤", "执行工作任务"]),
    ("外卖平台是否对骑手侵权承担替代责任或相应责任", ["平台", "外卖", "骑手", "雇主责任", "用人单位责任", "替代责任"]),
    ("骑手与平台之间法律关系如何认定", ["平台用工", "算法派单", "劳动关系", "劳务关系", "承揽", "管理控制"]),
    ("行人人身损害赔偿与交通事故责任如何分担", ["行人", "交通事故", "人身损害", "责任分担"]),
    ("宠物寄养期间走失是否构成保管或服务违约", ["宠物", "寄养", "走失", "保管", "看护"]),
    ("宠物店是否尽到安全看护和管理义务", ["宠物店", "看护", "管理义务", "安全保障", "走失"]),
    ("宠物走失损失如何证明和计算", ["宠物", "走失", "赔偿范围", "损失证明"]),
    ("公司能否证明股东查账具有不正当目的并可能损害公司合法利益", ["查账", "目的不正当", "竞争企业", "公司利益"]),
    ("近三年会计账簿和会计凭证是否属于可查阅范围", ["会计账簿", "会计凭证", "原始凭证", "查阅"]),
    ("IMEI码、序列号、激活状态、鉴定意见等证据能否证明商品来源或真伪", ["IMEI", "序列号", "激活", "鉴定", "仿品", "商品同一性"]),
    ("渠道串货与假货、翻新机或不符合约定之间应如何区分", ["渠道串货", "串货", "假货", "翻新机", "官方保修"]),
    ("卖家是否构成欺诈并应承担退货退款及三倍赔偿责任", ["假货", "正品", "欺诈", "三倍赔偿", "退一赔三"]),
    ("平台仅提供卖家信息是否免责，已有多次类似投诉时是否属于知道或应当知道", ["平台", "卖家信息", "多次投诉", "知道或应当知道", "下架"]),
    ("未办理产权过户时受让方是否已经取得足以排除执行的民事权益", ["离婚协议", "未过户", "执行异议", "排除执行"]),
    ("涉案债务是否属于夫妻共同债务以及该问题对解除查封请求有何影响", ["共同债务", "个人债务", "解除查封", "共同经营"]),
    ("物业公司应否公开广告合同、收入、支出及使用情况", ["物业公司", "广告收入", "公布账目", "公示"]),
    ("广告总收入扣除合理成本后的可返还收益如何审计和计算", ["公共收益", "合理成本", "维修支出", "返还收益", "审计"]),
]


DOMAIN_FALLBACKS = {
    "股东知情权": {
        "cause": "股东知情权纠纷",
        "behaviors": ["股东书面请求查阅公司资料", "公司以目的不正当为由拒绝"],
        "subjects": ["有限责任公司股东", "公司"],
        "liabilities": ["提供查阅义务", "正当目的审查", "商业秘密保护义务"],
        "damage_types": ["股东知情权受阻", "公司经营信息与商业秘密风险"],
        "issues": [
            "股东是否履行书面请求并说明查阅目的等前置程序",
            "公司能否证明股东查账具有不正当目的并可能损害公司合法利益",
            "股东同时经营竞争企业是否当然构成拒绝查阅的正当理由",
            "近三年会计账簿和会计凭证是否属于可查阅范围",
            "股东对会计账簿及凭证的复制请求是否具有明确法律或章程依据",
        ],
    },
    "网络购物": {
        "cause": "信息网络买卖合同纠纷",
        "behaviors": ["网络购买商品", "商品真实性或品质承诺争议"],
        "subjects": ["消费者", "网络商品销售者", "电子商务平台经营者"],
        "liabilities": ["退货退款责任", "经营者欺诈惩罚性赔偿责任", "平台知道或应当知道时的相应责任"],
        "damage_types": ["购货款损失", "三倍价款惩罚性赔偿", "合理鉴定费用"],
        "issues": [
            "涉案商品是否符合卖家关于官方正品、全新或品质状况的承诺",
            "IMEI码、序列号、激活状态、鉴定意见等证据能否证明商品来源或真伪",
            "渠道串货与假货、翻新机或不符合约定之间应如何区分",
            "卖家是否构成欺诈并应承担退货退款及三倍赔偿责任",
            "平台仅提供卖家信息是否免责，已有多次类似投诉时是否属于知道或应当知道",
        ],
    },
    "离婚房产执行": {
        "cause": "执行异议之诉 / 离婚后财产纠纷",
        "behaviors": ["离婚协议约定房产归属", "未过户房产被债权人申请查封"],
        "subjects": ["离婚协议取得房产一方", "登记权利人", "申请执行债权人"],
        "liabilities": ["离婚协议履行责任", "不动产登记与权利对抗", "执行排除责任"],
        "damage_types": ["房产被查封风险", "协议财产权利无法实现", "债权实现冲突"],
        "issues": [
            "离婚协议关于房产归属的约定是否真实有效",
            "未办理产权过户时受让方是否已经取得足以排除执行的民事权益",
            "未及时办理过户是否存在可归责于受让方的过错",
            "申请执行债权的形成时间、性质及债权人信赖利益如何影响权利顺位",
            "涉案债务是否属于夫妻共同债务以及该问题对解除查封请求有何影响",
        ],
    },
    "物业公共收益": {
        "cause": "物业服务合同纠纷 / 业主共有权纠纷",
        "behaviors": ["物业经营共有部分广告位", "公共收益未公示或分配"],
        "subjects": ["业主委员会或全体业主", "物业服务企业"],
        "liabilities": ["公共收益报告与公示义务", "返还共有收益义务", "合理成本扣除与账目说明义务"],
        "damage_types": ["业主公共收益损失", "共有资金账目不明", "合理经营管理成本争议"],
        "issues": [
            "电梯间广告位是否属于业主共有部分及其收益是否归业主共有",
            "业委会是否取得业主大会授权并具有提起诉讼的主体资格",
            "物业公司应否公开广告合同、收入、支出及使用情况",
            "物业公司能否以收益用于公共维修为由拒绝返还或结算",
            "广告总收入扣除合理成本后的可返还收益如何审计和计算",
        ],
    },
    "商铺租赁": {
        "cause": "房屋租赁合同纠纷",
        "behaviors": ["商铺租赁合同履行", "拖欠租金或提前搬离"],
        "subjects": ["商铺出租人", "商铺承租人"],
        "liabilities": ["支付租金责任", "合同解除责任", "违约金及押金结算责任"],
        "damage_types": ["欠付租金", "违约金或空置损失", "押金返还或抵扣争议"],
        "issues": [
            "商圈人流量下降是否属于正常经营风险或构成情势变更",
            "承租人未经协商自行搬离是否构成违约",
            "租赁合同应否解除以及解除时间如何确定",
            "欠付租金和违约金的范围及金额如何认定",
            "租赁押金应返还、没收还是用于抵扣欠租及损失",
        ],
    },
    "工业品买卖": {
        "cause": "买卖合同纠纷",
        "behaviors": ["工业品采购与交付", "质量异议及尾款拒付"],
        "subjects": ["出卖人或供应商", "买受人或采购方"],
        "liabilities": ["支付货款责任", "质量瑕疵担保责任", "违约损害赔偿责任"],
        "damage_types": ["未付货款及逾期利息", "产品质量损失", "可证明的下游退货或替换损失"],
        "issues": [
            "出卖人是否依约交付符合质量标准的芯片或工业品",
            "买受人是否在约定或合理期限内提出质量异议",
            "缺少第三方检测报告时质量不合格能否通过其他证据证明",
            "买受人能否以质量问题拒付全部或部分尾款",
            "下游客户退货损失与涉案产品质量问题之间是否存在因果关系且属于可预见损失",
        ],
    },
    "相邻关系": {
        "cause": "相邻关系纠纷 / 排除妨害纠纷",
        "behaviors": ["安装空调外机", "噪声、振动或滴水侵扰"],
        "subjects": ["受影响业主", "空调外机安装业主"],
        "liabilities": ["停止侵害", "排除妨害", "损害赔偿责任"],
        "damage_types": ["居住安宁受影响", "噪声或振动侵扰", "可证明的实际损失"],
        "issues": [
            "空调外机的安装位置是否对相邻住户构成妨害",
            "噪声、振动或滴水是否超过相邻住户合理容忍限度",
            "已采取减震措施是否足以排除实际侵扰",
            "能否判令移机、整改或采取其他排除妨害措施",
            "精神损害赔偿是否具有严重损害后果等事实依据",
        ],
    },
    "道路交通事故": {
        "cause": "机动车交通事故责任纠纷",
        "behaviors": ["机动车驾驶行为", "道路交通事故"],
        "subjects": ["机动车驾驶人", "受伤行人", "车辆保险人"],
        "liabilities": ["交通事故侵权责任", "人身损害赔偿责任", "保险赔偿责任"],
        "damage_types": ["医疗费", "误工费等人身损害", "精神损害抚慰金"],
        "issues": [
            "机动车驾驶人未在人行横道前减速是否构成过错",
            "交通事故责任认定书对民事责任划分有何影响",
            "行人看手机等行为是否构成过错并足以减轻机动车一方责任",
            "医疗费、误工费等人身损害赔偿项目如何认定",
            "精神损害抚慰金是否具备支持条件及金额如何确定",
        ],
    },
    "民间借贷": {
        "cause": "民间借贷纠纷",
        "behaviors": ["民间借贷", "借款利息约定"],
        "subjects": ["出借人", "借款人"],
        "liabilities": ["返还借款本金", "支付合法利息", "逾期还款责任"],
        "damage_types": ["借款本金损失", "合法利息损失", "逾期还款损失"],
        "issues": [
            "借贷关系及实际交付的借款本金能否证明",
            "双方约定的借款利率是否超过司法保护范围",
            "已经支付的利息应如何认定和抵扣",
            "逾期利息、违约金及其他费用能否同时支持",
        ],
    },
    "房屋租赁": {
        "cause": "房屋租赁合同纠纷",
        "behaviors": ["房屋租赁", "押金返还"],
        "subjects": ["出租人", "承租人"],
        "liabilities": ["合同责任", "返还责任", "损失赔偿责任"],
        "damage_types": ["押金损失", "租金或费用损失", "房屋损坏争议"],
        "issues": [
            "租赁押金是否具备返还条件",
            "出租人扣除押金是否具有合同和事实依据",
            "自然损耗与承租人造成的房屋损坏如何区分",
            "押金扣除金额及实际损失应由谁举证",
        ],
    },
    "劳动争议": {
        "cause": "劳动合同纠纷",
        "behaviors": ["劳动合同履行", "用工管理"],
        "subjects": ["劳动者", "用人单位"],
        "liabilities": ["劳动合同责任", "工资支付责任", "经济补偿或赔偿责任"],
        "damage_types": ["工资损失", "加班费", "经济补偿金或赔偿金"],
        "issues": [
            "双方是否存在劳动关系",
            "用人单位的处理是否具有事实和制度依据",
            "解除、工资或加班争议的举证责任如何分配",
            "经济补偿或赔偿范围如何计算",
        ],
    },
    "教育培训": {
        "cause": "教育培训合同纠纷",
        "behaviors": ["教育培训服务", "预付费履约"],
        "subjects": ["培训机构", "学员或家长"],
        "liabilities": ["服务合同责任", "退费责任", "违约赔偿责任"],
        "damage_types": ["未履行课程费用", "退费损失", "其他合理支出"],
        "issues": [
            "培训机构是否按约提供课程",
            "停课或无法继续履行是否构成根本违约",
            "未上课程费用应如何计算和返还",
            "不退费等格式条款是否有效",
        ],
    },
    "医疗美容": {
        "cause": "医疗服务合同纠纷 / 消费者权益保护纠纷",
        "behaviors": ["医疗美容服务", "效果宣传或诊疗行为"],
        "subjects": ["医疗美容机构", "消费者或患者"],
        "liabilities": ["医疗服务责任", "告知义务", "损害赔偿责任"],
        "damage_types": ["医疗费用损失", "人身损害", "误导宣传造成的交易损失"],
        "issues": [
            "医疗美容机构是否充分履行告知和风险提示义务",
            "宣传内容或效果承诺是否构成合同内容或误导",
            "诊疗行为与损害后果之间是否存在因果关系",
            "退费及赔偿范围如何认定",
        ],
    },
}


QUESTION_BANK = {
    "主播": "主播是否承担责任，通常取决于其是否实际参与宣传、是否以推荐或证明方式影响交易、是否尽到合理审查义务，以及是否存在佣金、坑位费等获利安排。",
    "连带": "连带责任不是当然成立。若主播与商家共同实施误导宣传，或明知、应知商品信息不实仍作推荐证明，法院更可能支持相应连带或共同责任。",
    "为什么": "裁判逻辑一般会从行为、过错、因果关系和损害四个层面展开：宣传是否不实，用户是否因该宣传购买，主体是否有审查能力与注意义务，损失是否可归责。",
    "平台": "平台责任通常看是否履行入驻审核、广告标识、投诉处置、下架整改等义务。平台若仅提供技术服务且及时处置，责任会明显减轻。",
    "原告": "支持消费者一方时，重点组织宣传截图、直播话术、购买链路、主播收益、商品检测或官方说明，以证明误导宣传和交易决定之间的因果关系。",
    "被告": "支持主播一方时，可强调主播仅作一般展示、未作专业保证、已核验合理资料、无实际销售分成，或者消费者损失与宣传内容之间缺少因果关系。",
}


@dataclass
class Case:
    title: str
    docket: str
    court: str
    date: str
    cause: str
    side: str
    facts: str
    holding: str
    reasoning: str
    result: str
    tags: list[str]
    support_for: str
    quote: str
    domain: str = "通用"
    source: str = "本地教学案例库"


@dataclass
class ParsedInput:
    raw: str
    behaviors: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    liabilities: list[str] = field(default_factory=list)
    legal_elements: dict[str, list[str]] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    query_terms: list[str] = field(default_factory=list)
    cause: str = ""
    domain: str = "通用"
    parse_success: bool = False
    parse_notice: str = ""


def classify_domain(text: str, tokens: list[str]) -> str:
    if any(word in text for word in ["股东知情权", "查阅会计账簿", "原始凭证", "查账"]) and any(
        word in text for word in ["股东", "公司", "大股东", "关联交易"]
    ):
        return "股东知情权"
    if any(word in text for word in ["购买", "网购", "收货", "卖家", "店铺", "旗舰店", "电商平台"]) and any(
        word in text
        for word in [
            "假货", "仿品", "正品", "官方正品", "假一赔三", "退一赔三", "三倍赔偿",
            "支持鉴定", "IMEI", "序列号", "无法激活", "串货", "翻新机",
        ]
    ):
        return "网络购物"
    if any(word in text for word in ["离婚协议", "协议离婚", "离婚财产"]) and any(
        word in text for word in ["房产", "房屋", "过户", "查封", "执行异议"]
    ):
        return "离婚房产执行"
    if any(word in text for word in ["业委会", "物业公司", "公共收益", "电梯广告", "广告位"]) and any(
        word in text for word in ["公示", "分配", "返还", "公布账目", "维修"]
    ):
        return "物业公共收益"
    if any(word in text for word in ["商铺", "店铺租赁", "门面", "门面房", "商业用房", "商场铺位", "经营场所"]):
        return "商铺租赁"
    if (
        any(word in text for word in ["芯片", "元器件", "零部件", "工业品", "采购", "供货", "供应商"])
        and any(word in text for word in ["货款", "尾款", "交货", "质量", "性能", "检测", "退货"])
    ):
        return "工业品买卖"
    if any(word in text for word in ["空调外机", "外机位", "相邻住户", "邻居噪声", "邻居噪音"]) or (
        any(word in text for word in ["邻居", "楼上", "楼下", "隔壁", "业主"])
        and any(word in text for word in ["噪声", "噪音", "震动", "振动", "滴水", "妨害"])
    ):
        return "相邻关系"
    if any(word in text for word in ["民间借贷", "借款", "借钱", "借条", "欠条", "出借", "高利贷", "利息太高", "利率太高"]):
        return "民间借贷"
    if "外卖" in text or "骑手" in text or "送餐" in text or "配送员" in text:
        return "外卖配送"
    if (
        any(word in text for word in ["交通事故", "驾车", "开车", "斑马线", "人行横道", "交警", "事故认定", "机动车"])
        and any(word in text for word in ["撞伤", "撞倒", "碰撞", "刮碰", "行人", "受伤"])
    ):
        return "道路交通事故"
    if "餐厅" in text or "餐饮" in text or "自带酒水" in text or "开瓶费" in text:
        return "餐饮消费"
    if "健身房" in text or "会员卡" in text or "预付卡" in text or "闭店" in text:
        return "健身预付卡"
    if "网约车" in text or "误机" in text or "绕路" in text:
        return "网约车服务"
    if "主播" in text or "直播" in text or "带货" in text:
        return "直播电商"
    if "房租" in text or "租房" in text or "租赁" in text or "押金" in text:
        return "房屋租赁"
    if "劳动" in text or "工资" in text or "加班" in text or "辞退" in text:
        return "劳动争议"
    if "医美" in text or "医疗美容" in text or "整形" in text:
        return "医疗美容"
    if "培训" in text or "补课" in text or "教育机构" in text:
        return "教育培训"
    if "宠物" in text or "寄养" in text or "猫" in text or "狗" in text:
        return "宠物服务"
    return "通用"


def load_external_cases(fallback: list[Case]) -> list[Case]:
    if not CASE_LIBRARY_PATH.exists():
        return fallback
    try:
        records = json.loads(CASE_LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"案例库读取失败，使用代码内置案例：{exc}")
        return fallback

    cases: list[Case] = []
    required = {"title", "docket", "court", "date", "cause", "facts", "holding", "reasoning", "result", "tags", "support_for", "quote"}
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            print(f"跳过第 {index} 条案例：不是对象")
            continue
        missing = required.difference(record)
        if missing:
            print(f"跳过第 {index} 条案例：缺少字段 {sorted(missing)}")
            continue
        cases.append(
            Case(
                title=str(record["title"]),
                docket=str(record["docket"]),
                court=str(record["court"]),
                date=str(record["date"]),
                cause=str(record["cause"]),
                side=str(record.get("side", record.get("support_for", ""))),
                facts=str(record["facts"]),
                holding=str(record["holding"]),
                reasoning=str(record["reasoning"]),
                result=str(record["result"]),
                tags=[str(tag) for tag in record.get("tags", [])],
                support_for=str(record["support_for"]),
                quote=str(record["quote"]),
                domain=str(record.get("domain", "通用")),
                source=str(record.get("source", "本地案例库")),
            )
        )
    return cases or fallback


CASES = [
    Case(
        title="教学示例一：消费者诉某直播主播、食品公司网络购物合同纠纷案",
        docket="示例案号 JX-2023-001",
        court="教学示例案例库",
        date="2023-09-18",
        cause="网络购物合同纠纷",
        side="消费者",
        facts="主播在直播间宣称涉案食品具有明显调理功效，并引导消费者通过直播链接购买。商品页面和检测资料未能证明相应功效。",
        holding="主播深度参与商品卖点介绍并获取推广收益，未对核心宣传内容尽合理审查义务，应与经营者承担相应赔偿责任。",
        reasoning="法院重点审查直播话术、主播身份、推广收益、消费者下单路径与商品真实信息之间的差距，认为宣传内容足以影响购买决定。",
        result="支持消费者部分赔偿请求，主播与商家在误导宣传范围内承担责任。",
        tags=["直播带货", "虚假宣传", "主播", "明知应知", "获利分成", "消费者权益", "连带责任"],
        support_for="消费者",
        quote="主播并非当然免责，是否担责取决于其参与程度、获利情况和审查义务履行情况。",
    ),
    Case(
        title="教学示例二：消费者诉某文化传媒公司、化妆品店产品宣传责任纠纷案",
        docket="示例案号 JX-2022-002",
        court="教学示例案例库",
        date="2022-12-06",
        cause="产品责任纠纷",
        side="消费者",
        facts="MCN机构安排达人直播推广化妆品，直播中使用绝对化用语并暗示医疗美容效果，消费者购买后认为效果与宣传不符。",
        holding="直播推广构成商业宣传，达人及其所属机构对明显夸大的功效表述负有审查和更正义务。",
        reasoning="法院认为普通消费者容易基于达人信任作出交易决定，MCN机构组织策划脚本并获得推广利益，应承担更高注意义务。",
        result="判令商家退款并赔偿，传媒公司在其参与宣传过错范围内承担补充赔偿责任。",
        tags=["直播带货", "虚假宣传", "广告代言", "MCN", "明知应知", "产品责任", "消费者权益"],
        support_for="消费者",
        quote="达人营销不应以流量信任替代事实核验。",
    ),
    Case(
        title="教学示例三：消费者诉某电商平台、保健品经营者信息网络买卖合同纠纷案",
        docket="示例案号 JX-2021-003",
        court="教学示例案例库",
        date="2021-10-22",
        cause="信息网络买卖合同纠纷",
        side="平台",
        facts="消费者主张平台应对入驻商家保健品功效虚假宣传承担连带赔偿责任，但平台在接到投诉后及时下架并提供经营者真实信息。",
        holding="平台已履行必要审核、提示和协助义务，现有证据不足以证明其参与虚假宣传或明知违法信息。",
        reasoning="平台责任应与其控制能力和过错程度相匹配，不能因平台提供交易空间而当然承担商家全部责任。",
        result="商家承担主要赔偿责任，驳回消费者要求平台连带赔偿的请求。",
        tags=["网络平台责任", "虚假宣传", "平台", "审核", "下架", "消费者权益"],
        support_for="平台或被告",
        quote="平台是否担责，应回到通知处置、审核能力和实际参与程度。",
    ),
    Case(
        title="教学示例四：消费者诉某主播网络直播购物损害赔偿纠纷案",
        docket="示例案号 JX-2024-004",
        court="教学示例案例库",
        date="2024-05-11",
        cause="网络直播购物损害赔偿纠纷",
        side="主播",
        facts="主播在直播中展示某品牌家电优惠信息，但未自行编辑产品参数，也未收取销售佣金。消费者主张参数误导导致损失。",
        holding="主播仅作一般商品展示，未作专业保证或核心性能承诺，且无证据证明其明知参数错误，不宜直接认定连带责任。",
        reasoning="法院区分普通展示与广告代言式推荐，认为消费者仍需证明主播过错与损害之间的因果关系。",
        result="商家承担退赔责任，消费者对主播的连带责任请求未获支持。",
        tags=["直播带货", "主播", "连带责任", "明知应知", "合同纠纷", "被告抗辩"],
        support_for="主播或被告",
        quote="主播责任不能脱离具体话术、收益关系和主观过错单独判断。",
    ),
    Case(
        title="教学示例五：消费者诉某珠宝直播间欺诈销售纠纷案",
        docket="示例案号 JX-2023-005",
        court="教学示例案例库",
        date="2023-11-29",
        cause="买卖合同纠纷",
        side="消费者",
        facts="直播间宣称珠宝为天然高等级材质并限时保真，主播多次以个人信誉作保证。鉴定结果显示商品等级与宣传明显不符。",
        holding="主播以个人信用对商品品质作保证，足以增强消费者信赖，应对未尽核验义务承担相应责任。",
        reasoning="法院将保真承诺、鉴定结论、直播成交链路和佣金收益作为相似要素，认定宣传行为与购买决定存在关联。",
        result="支持退货退款和惩罚性赔偿，主播与商家承担连带赔偿责任。",
        tags=["直播带货", "虚假宣传", "主播", "连带责任", "获利分成", "消费者权益", "欺诈"],
        support_for="消费者",
        quote="以个人信誉作商品品质保证，会显著提高主播注意义务。",
    ),
    Case(
        title="教学示例六：消费者诉某短视频达人广告代言责任纠纷案",
        docket="示例案号 JX-2022-006",
        court="教学示例案例库",
        date="2022-08-15",
        cause="广告责任纠纷",
        side="消费者",
        facts="短视频达人发布种草视频，称某减肥产品安全有效并附购买链接。后监管部门认定该产品广告含有违法功效宣传。",
        holding="达人以自身体验名义推荐商品，实质属于广告代言，应对未使用或未核验的推荐内容承担责任。",
        reasoning="法院强调广告代言与普通信息分享的边界，认为购买链接、佣金和商业合作标识是判断商业推广的重要事实。",
        result="判令经营者赔偿，达人在广告代言过错范围内承担连带责任。",
        tags=["广告代言", "虚假宣传", "短视频", "达人", "明知应知", "获利分成", "连带责任"],
        support_for="消费者",
        quote="种草内容一旦进入商业推广链条，即需接受广告责任规则评价。",
    ),
    Case(
        title="教学示例七：会员诉某健身房预付卡余额返还纠纷案",
        docket="示例案号 JX-2024-007",
        court="教学示例案例库",
        date="2024-04-16",
        cause="服务合同纠纷",
        side="消费者",
        facts="消费者办理健身房年卡并充值私教课程，健身房突然闭店且未提供同等替代服务，会员要求退还卡内余额和剩余课时费用。",
        holding="经营者停止提供约定健身服务，致使合同目的无法实现，消费者有权解除合同并要求返还未消费的预付款。",
        reasoning="法院重点审查闭店原因、合同履行期限、剩余服务价值、经营者是否提前通知及是否提供合理替代方案。不退费格式条款不能排除消费者依法解除合同和请求返还余额的权利。",
        result="支持会员解除合同，判令健身房返还会员卡余额及未履行私教课费用。",
        tags=["健身服务", "预付卡", "闭店停业", "余额返还", "合同纠纷", "消费者权益", "违约赔偿"],
        support_for="消费者",
        quote="预付式消费中，经营者停止履行主要服务义务的，未消费余额应依法返还。",
    ),
    Case(
        title="教学示例八：健身房转让后会员卡退费责任纠纷案",
        docket="示例案号 JX-2023-008",
        court="教学示例案例库",
        date="2023-07-21",
        cause="服务合同纠纷",
        side="消费者",
        facts="健身房将门店转让给新经营者后，原会员被告知只能按新价格折算使用，不能退还原会员卡余额。消费者起诉原经营者和新经营者。",
        holding="门店转让不能当然免除原经营者对既有会员合同的责任；新经营者实际承接会员服务的，也可能在承接范围内承担继续履行或退费责任。",
        reasoning="法院比较转让协议、会员通知、收款主体、门店招牌延续和会员数据交接情况，判断消费者是否同意债务转移及新经营者是否承接服务义务。",
        result="判令原经营者返还未消费余额，新经营者对其承诺承接的服务范围承担相应责任。",
        tags=["健身服务", "预付卡", "余额返还", "转让", "合同纠纷", "消费者权益"],
        support_for="消费者",
        quote="经营主体变化不能以内部转让安排对抗消费者的既有合同权益。",
    ),
    Case(
        title="教学示例九：会员诉健身机构私教课不退费格式条款纠纷案",
        docket="示例案号 JX-2022-009",
        court="教学示例案例库",
        date="2022-10-09",
        cause="服务合同纠纷",
        side="消费者",
        facts="会员购买大额私教课后因健身机构长期更换教练、课程安排困难而要求退费，合同载明“私教课售出概不退款”。",
        holding="经营者未稳定提供约定课程安排，构成服务履行瑕疵；“概不退款”条款若未合理提示且实质排除消费者主要权利，不能作为拒绝退费的当然依据。",
        reasoning="法院从格式条款提示说明义务、服务履行质量、剩余课程数量和双方过错程度确定退费范围。",
        result="支持退还未上私教课费用，酌情扣除已履行课程费用和合理管理成本。",
        tags=["健身服务", "预付卡", "余额返还", "格式条款", "合同纠纷", "消费者权益"],
        support_for="消费者",
        quote="预付课程的退费判断，应回到服务是否实际履行以及格式条款是否公平有效。",
    ),
]

CASES = load_external_cases(CASES)


def tokenize(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    tokens: list[str] = []
    for concept, words in LEGAL_KEYWORDS.items():
        if any(word in text for word in words):
            tokens.append(concept)
            tokens.extend([word for word in words if word in text])
    tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", text))
    return sorted(set(tokens), key=tokens.index)


def mark_parse_failed(parsed: ParsedInput, notice: str | None = None) -> ParsedInput:
    parsed.parse_success = False
    parsed.parse_notice = notice or "当前案例库没有找到足够相近的案例，已停止生成案由和争议焦点，避免误导。"
    parsed.cause = ""
    parsed.behaviors = []
    parsed.subjects = []
    parsed.liabilities = []
    parsed.legal_elements = {}
    parsed.issues = []
    return parsed


def parse_case_input(text: str) -> ParsedInput:
    tokens = tokenize(text)
    parsed = ParsedInput(raw=text)
    parsed.domain = classify_domain(text, tokens)
    parsed.parse_success = parsed.domain != "通用"

    parsed.behaviors = [key for key in ["直播带货", "虚假宣传", "广告代言", "产品责任", "网约车服务", "绕路", "健身服务", "闭店停业", "餐饮服务", "禁止自带酒水", "外卖配送", "交通事故", "宠物寄养"] if key in tokens]
    parsed.subjects = [word for word in ["主播", "达人", "商家", "平台", "MCN", "消费者", "网约车司机", "司机", "乘客", "健身房", "会员", "餐厅", "饭店", "顾客", "外卖骑手", "骑手", "配送员", "行人"] if word in text]
    parsed.liabilities = [key for key in ["连带责任", "侵权责任", "消费者权益", "网络平台责任", "运输合同", "违约赔偿", "预付卡", "余额返还", "格式条款", "平台用工", "用人单位责任"] if key in tokens]
    if parsed.domain == "外卖配送":
        parsed.liabilities = ["侵权责任", "平台责任/用人单位责任", "交通事故责任"]
    domain_fallback = DOMAIN_FALLBACKS.get(parsed.domain)
    if domain_fallback:
        parsed.behaviors = list(domain_fallback["behaviors"])
        domain_subjects = [subject for subject in domain_fallback["subjects"] if subject in text]
        parsed.subjects = parsed.subjects or domain_subjects or list(domain_fallback["subjects"])
        parsed.liabilities = list(domain_fallback["liabilities"])

    parsed.legal_elements = {
        "行为性质": parsed.behaviors or ["案涉合同履行或侵权行为"],
        "责任主体": parsed.subjects or ["请求权人", "被请求承担责任的主体"],
        "责任类型": parsed.liabilities or ["合同责任或侵权责任"],
        "损害类型": (
            list(domain_fallback["damage_types"])
            if domain_fallback
            else [key for key in ["消费者权益", "产品责任", "合同纠纷", "误机损失", "预付卡", "余额返还", "格式条款", "交通事故"] if key in tokens]
            or ["实际损失及可证明的相关费用"]
        ),
    }
    if parsed.domain == "外卖配送":
        parsed.legal_elements = {
            "行为性质": parsed.behaviors or ["送餐履约过程中的交通侵权行为"],
            "责任主体": parsed.subjects or ["外卖骑手", "外卖平台", "受害行人"],
            "责任类型": parsed.liabilities,
            "损害类型": ["人身损害", "医疗费/误工费/护理费等损失", "交通事故损害"],
        }
    if parsed.domain == "宠物服务":
        parsed.legal_elements = {
            "行为性质": parsed.behaviors or ["宠物寄养或托管服务履行瑕疵"],
            "责任主体": ["宠物店/寄养服务提供者", "宠物主人"],
            "责任类型": ["服务合同违约责任", "保管合同责任", "过错赔偿责任"],
            "损害类型": ["宠物走失损失", "寻找费用", "合理精神利益相关损失需谨慎论证"],
        }

    issues = []
    for issue, markers in ISSUE_TEMPLATES:
        if any(marker in text or marker in tokens for marker in markers):
            issues.append(issue)
    if domain_fallback:
        issues = list(domain_fallback["issues"])
    elif not issues:
        issues = (
            ["案涉行为的法律性质如何认定", "相关主体是否存在违约或过错", "损失、因果关系及责任范围如何认定"]
        )
    if "网约车" in text or "误机" in text or "绕路" in text:
        issues = [issue for issue in issues if not any(word in issue for word in ["主播", "商家", "直播"])]
    if "健身房" in text or "会员卡" in text or "预付卡" in text or "闭店" in text:
        issues = [issue for issue in issues if not any(word in issue for word in ["主播", "直播", "网约车", "误机"])]
    if "餐厅" in text or "餐饮" in text or "自带酒水" in text or "开瓶费" in text:
        issues = [issue for issue in issues if not any(word in issue for word in ["主播", "直播", "网约车", "误机", "健身房", "会员卡"])]
    if parsed.domain == "外卖配送":
        issues = [
            "骑手送餐途中撞伤行人是否属于执行工作任务",
            "外卖平台是否对骑手侵权承担替代责任或相应责任",
            "骑手与平台之间法律关系如何认定",
            "行人人身损害赔偿与交通事故责任如何分担",
        ]
    if parsed.domain == "宠物服务":
        issues = [
            "宠物寄养期间走失是否构成保管或服务违约",
            "宠物店是否尽到安全看护和管理义务",
            "宠物走失损失如何证明和计算",
        ]
    parsed.issues = issues[:5]

    if parsed.domain == "外卖配送":
        parsed.cause = "机动车交通事故责任纠纷 / 提供劳务者致害责任纠纷 / 网络服务平台责任纠纷"
    elif parsed.domain == "宠物服务":
        parsed.cause = "服务合同纠纷 / 保管合同纠纷 / 财产损害赔偿纠纷"
    elif "餐厅" in text or "餐饮" in text or "自带酒水" in text or "开瓶费" in text:
        parsed.cause = "餐饮服务合同纠纷 / 消费者权益保护纠纷"
    elif "健身房" in text or "会员卡" in text or "预付卡" in text or "闭店" in text:
        parsed.cause = "服务合同纠纷 / 预付式消费纠纷 / 消费者权益保护纠纷"
    elif "网约车" in text or "误机" in text or "绕路" in text:
        parsed.cause = "网络预约出租汽车服务合同纠纷 / 旅客运输合同纠纷"
    elif domain_fallback:
        parsed.cause = str(domain_fallback["cause"])
    elif "平台" in text:
        parsed.cause = "网络服务合同纠纷 / 消费者权益保护纠纷"
    elif "主播" in text or "直播" in text:
        parsed.cause = "网络直播购物损害赔偿纠纷 / 网络购物合同纠纷"

    parsed.query_terms = sorted(set(tokens + parsed.behaviors + parsed.subjects + parsed.liabilities), key=(tokens + parsed.behaviors + parsed.subjects + parsed.liabilities).index)
    if not parsed.parse_success:
        mark_parse_failed(parsed, "未能从本地规则和案例库中可靠识别该案情，已停止生成案由和争议焦点，避免误导。")
    return parsed


def score_case(parsed: ParsedInput, case: Case) -> tuple[float, list[str], list[str]]:
    query_terms = set(parsed.query_terms)
    tag_hits = sorted(query_terms.intersection(case.tags))
    issue_hits = []
    case_text = " ".join([case.facts, case.holding, case.reasoning, " ".join(case.tags)])
    for issue in parsed.issues:
        markers = next((m for name, m in ISSUE_TEMPLATES if name == issue), [])
        if any(marker in case_text for marker in markers):
            issue_hits.append(issue)

    query_vector = set(tokenize(parsed.raw))
    case_vector = set(tokenize(case_text))
    lexical = len(query_vector.intersection(case_vector)) / max(1, len(query_vector.union(case_vector)))
    tag_score = len(tag_hits) / max(1, len(query_terms))
    issue_score = len(issue_hits) / max(1, len(parsed.issues))
    recency = (datetime.fromisoformat(case.date).year - 2020) / 6

    score = 0.45 * tag_score + 0.35 * issue_score + 0.15 * lexical + 0.05 * max(0, min(recency, 1))
    if "连带责任" in parsed.query_terms and "连带责任" in case.tags:
        score += 0.08
    if ("主播" in parsed.subjects or "直播" in parsed.raw) and "主播" in case.tags:
        score += 0.06
    salient_facts = [
        "IMEI", "无法激活", "多次投诉", "运动鞋", "仿品", "翻新机",
        "渠道串货", "全国联保", "投诉", "执行异议", "原始凭证", "电梯广告",
    ]
    salient_hits = sum(1 for fact in salient_facts if fact in parsed.raw and fact in case_text)
    score += min(0.12, salient_hits * 0.04)
    return min(score, 1.0), tag_hits, issue_hits


def summarize_match(
    parsed: ParsedInput,
    case: Case,
    tag_hits: list[str],
    issue_hits: list[str],
    final_score: float | None = None,
) -> dict[str, Any]:
    differences = []
    is_gym = any(term in parsed.raw for term in ["健身房", "会员卡", "预付卡", "闭店"])
    is_ride_hailing = any(term in parsed.raw for term in ["网约车", "误机", "绕路"])
    is_restaurant = any(term in parsed.raw for term in ["餐厅", "餐饮", "自带酒水", "开瓶费"])
    is_delivery = parsed.domain == "外卖配送"
    if "获利分成" in parsed.query_terms and "获利分成" not in case.tags:
        differences.append("该案未突出主播实际获利或销售分成。")
    if "平台" in parsed.subjects and "平台" not in case.tags and not is_gym and not is_delivery:
        differences.append("该案主要讨论主播或商家责任，平台责任部分较弱。")
    if "连带责任" in parsed.query_terms and "连带责任" not in case.tags:
        differences.append("该案没有直接支持连带责任，更适合用于责任边界分析。")
    if is_gym and "闭店停业" not in case.tags:
        differences.append("该案未直接涉及突然闭店，需重点比较服务无法继续履行的事实。")
    if is_gym and "预付卡" not in case.tags:
        differences.append("该案未直接涉及预付卡余额，退费计算规则参考价值较弱。")
    if is_ride_hailing and "误机损失" not in case.tags:
        differences.append("该案未直接涉及误机损失，需另找可预见损失和损失证明类案例。")
    if is_delivery and "外卖配送" not in case.tags:
        differences.append("该案未直接涉及外卖配送场景，需重点比较平台控制、派单管理和履职过程。")
    if is_delivery and "交通事故" not in case.tags:
        differences.append("该案未直接涉及交通事故责任，行人人身损害赔偿规则参考价值较弱。")
    if not differences:
        if is_gym:
            differences.append("核心事实与当前问题较接近，可直接比较闭店原因、剩余余额、服务替代方案和不退费条款。")
        elif is_ride_hailing:
            differences.append("核心事实与当前问题较接近，可直接比较路线偏离、延误原因、平台责任和误机损失证明。")
        elif is_restaurant:
            differences.append("核心事实与当前问题较接近，可直接比较店堂告示、格式条款、消费者选择权和是否变相强制消费。")
        elif is_delivery:
            differences.append("核心事实与当前问题较接近，可直接比较送餐是否属于履职过程、平台控制程度、骑手过错和行人损害。")
        else:
            differences.append("核心事实与当前问题较接近，可直接比较宣传参与程度、审查义务和责任承担。")

    claimant_markers = ["消费者", "受害", "行人", "乘客", "劳动者", "承租人", "会员"]
    angle = "可用于论证请求方主张" if any(marker in case.support_for for marker in claimant_markers) else "可用于区分或支持被告抗辩"
    if "主播" in case.support_for:
        angle = "可用于论证主播并非当然承担连带责任"

    return {
        "title": case.title,
        "docket": case.docket,
        "court": case.court,
        "date": case.date,
        "cause": case.cause,
        "domain": case.domain,
        "source": case.source,
        "score": round((final_score if final_score is not None else score_case(parsed, case)[0]) * 100),
        "similarities": [
            f"命中要素：{('、'.join(tag_hits) if tag_hits else '宣传行为、交易损害、责任主体')}",
            f"对应争议：{('；'.join(issue_hits) if issue_hits else '行为性质与责任分配')}",
        ],
        "differences": differences,
        "holding": case.holding,
        "summary": [
            f"案情概括：{case.facts}",
            f"争议焦点：{('；'.join(issue_hits) if issue_hits else '推广主体是否应对宣传内容承担责任')}。",
            f"法院观点：{case.reasoning}",
            f"裁判结果：{case.result}",
            f"可引用要旨：{case.quote}",
        ],
        "angle": angle,
        "support_for": case.support_for,
    }


def _first_text(record: dict[str, Any], *keys: str, default: str = "") -> str:
    """从不同法律数据库可能使用的字段名中取第一个非空文本。"""
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = "、".join(str(item) for item in value if item is not None)
        value = str(value).strip()
        if value:
            return value
    return default


def _normalize_date(value: Any) -> str:
    """统一外部数据库日期，避免日期格式不规范导致排序或打分报错。"""
    raw = str(value or "").strip()
    if not raw:
        return "2024-01-01"
    match = re.search(r"(20\d{2}|19\d{2})[-年./](\d{1,2})[-月./](\d{1,2})", raw)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    match = re.search(r"(20\d{2}|19\d{2})", raw)
    if match:
        return f"{match.group(1)}-01-01"
    return "2024-01-01"


def _normalize_tags(value: Any, extra_text: str = "") -> list[str]:
    tags: list[str] = []
    if isinstance(value, list):
        tags.extend(str(item).strip() for item in value if str(item).strip())
    elif isinstance(value, str):
        tags.extend(item.strip() for item in re.split(r"[,，;；、\s]+", value) if item.strip())
    tags.extend(tokenize(extra_text))
    return sorted(set(tags), key=tags.index)[:18]


def _extract_records(data: Any) -> list[dict[str, Any]]:
    """兼容常见 API 返回结构：list、results、data.list、data.records 等。"""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    candidate_keys = ["results", "cases", "items", "records", "documents", "list"]
    for key in candidate_keys:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    nested = data.get("data")
    if isinstance(nested, list):
        return [item for item in nested if isinstance(item, dict)]
    if isinstance(nested, dict):
        for key in candidate_keys:
            value = nested.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _legal_kb_record_to_case(record: dict[str, Any], parsed: ParsedInput) -> Case:
    title = _first_text(record, "title", "caseName", "case_name", "name", "案件名称", default="外部法律知识库案例")
    docket = _first_text(record, "docket", "caseNo", "case_no", "caseNumber", "案号", default="外部库未返回案号")
    court = _first_text(record, "court", "courtName", "court_name", "法院", default="外部法律知识库")
    date = _normalize_date(_first_text(record, "date", "judgmentDate", "judgementDate", "trialDate", "publishDate", "裁判日期", "发布日期"))
    cause = _first_text(record, "cause", "caseCause", "案由", default=parsed.cause)
    facts = _first_text(record, "facts", "fact", "basicFacts", "summary", "caseSummary", "案情", "基本案情", default="外部知识库返回了该案例，但未提供案情摘要。")
    holding = _first_text(record, "holding", "rule", "裁判要旨", "裁判规则", "gist", "keyPoint", default="外部知识库未返回明确裁判要旨，请回到授权数据库核验全文。")
    reasoning = _first_text(record, "reasoning", "reason", "courtView", "judgmentReason", "裁判理由", "法院认为", default=holding)
    result = _first_text(record, "result", "judgmentResult", "裁判结果", "判决结果", default="外部知识库未返回裁判结果。")
    quote = _first_text(record, "quote", "excerpt", "裁判观点", "可引用裁判观点", default=holding)
    source = _first_text(record, "source", "sourceName", "database", "url", "link", "来源", default="授权法律知识库 API")
    support_for = _first_text(record, "support_for", "supportFor", "position", "倾向", default="需结合案情判断")
    extra_text = " ".join([title, cause, facts, holding, reasoning, result, parsed.raw])
    return Case(
        title=title,
        docket=docket,
        court=court,
        date=date,
        cause=cause,
        side=support_for,
        facts=facts,
        holding=holding,
        reasoning=reasoning,
        result=result,
        tags=_normalize_tags(record.get("tags") or record.get("keywords") or record.get("关键词"), extra_text),
        support_for=support_for,
        quote=quote,
        domain=_first_text(record, "domain", "领域", default=parsed.domain),
        source=source,
    )


def build_legal_kb_payload(parsed: ParsedInput) -> dict[str, Any]:
    """发送给法律知识库 API 的标准请求体。可根据数据库文档在这里改字段名。"""
    return {
        "query": " ".join(parsed.query_terms[:10]) or parsed.raw,
        "raw_text": parsed.raw,
        "cause": parsed.cause,
        "domain": parsed.domain,
        "issues": parsed.issues,
        "keywords": parsed.query_terms[:15],
        "top_k": LEGAL_KB_TOP_K,
    }


def analyze_case_with_ai(parsed: ParsedInput) -> tuple[ParsedInput, str]:
    """Let the configured OpenAI-compatible legal model refine cause and keywords."""
    result = LEGAL_KB_CLIENT.analyze(build_legal_kb_payload(parsed))
    if result.analysis:
        parsed = apply_legal_kb_analysis(parsed, result.analysis)
    return parsed, result.notice


def apply_legal_kb_analysis(parsed: ParsedInput, analysis: dict[str, Any]) -> ParsedInput:
    """Merge API analysis into rule-based analysis after validating its shape."""
    if not analysis:
        return parsed

    for field_name in ("cause", "domain"):
        value = analysis.get(field_name)
        if isinstance(value, str) and value.strip():
            setattr(parsed, field_name, value.strip())

    for field_name in ("behaviors", "subjects", "liabilities", "issues", "query_terms"):
        value = analysis.get(field_name)
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            if cleaned:
                setattr(parsed, field_name, cleaned[:15])

    elements = analysis.get("legal_elements")
    if isinstance(elements, dict):
        cleaned_elements = {
            str(key): [str(item).strip() for item in value if str(item).strip()]
            for key, value in elements.items()
            if isinstance(value, list)
        }
        if cleaned_elements:
            parsed.legal_elements = cleaned_elements
    if parsed.cause and parsed.issues:
        parsed.parse_success = True
        parsed.parse_notice = ""
    return parsed


def deduplicate_cases(cases: list[Case]) -> list[Case]:
    """Prefer API records when local and external candidates describe the same case."""
    unique: dict[str, Case] = {}
    for case in cases:
        docket = re.sub(r"\s+", "", case.docket)
        has_real_docket = docket and "未返回案号" not in docket and "示例案号" not in docket
        key = docket if has_real_docket else case.title.strip()
        if key not in unique or "API" in case.source or case.source.startswith("http"):
            unique[key] = case
    return list(unique.values())


def rank_cases(parsed: ParsedInput, candidates: list[Case]) -> list[tuple[float, Case, list[str], list[str]]]:
    ranked = []
    for case in candidates:
        score, tag_hits, issue_hits = score_case(parsed, case)
        if parsed.domain != "通用" and case.domain == parsed.domain:
            score += 0.12
        if "本地" not in case.source and "教学" not in case.source:
            score += 0.06
        ranked.append((min(score, 1.0), case, tag_hits, issue_hits))
    ranked.sort(key=lambda item: (-item[0], item[1].date), reverse=False)
    return ranked


def search_cases(text: str) -> dict[str, Any]:
    parsed = parse_case_input(text)
    parsed, ai_analysis_notice = analyze_case_with_ai(parsed)
    legal_kb_notice = ai_analysis_notice

    if parsed.parse_success:
        local_candidates = CASES
        ranked = rank_cases(parsed, local_candidates)
        reliable_matches = [item for item in ranked if item[0] >= 0.22]
        cards = [
            summarize_match(parsed, case, tag_hits, issue_hits, score)
            for score, case, tag_hits, issue_hits in reliable_matches[:3]
        ]
        if not cards:
            mark_parse_failed(parsed)
    else:
        cards = []

    if cards:
        local_match_notice = ""
    elif not parsed.parse_success:
        local_match_notice = parsed.parse_notice
    else:
        local_match_notice = f"本地案例库暂未找到“{parsed.domain}”领域下足够相近的类案。请使用下方多源检索 Agent 扩展检索。"

    return {
        "parsed": {
            "success": parsed.parse_success,
            "notice": parsed.parse_notice,
            "cause": parsed.cause,
            "domain": parsed.domain,
            "behaviors": parsed.behaviors,
            "subjects": parsed.subjects,
            "liabilities": parsed.liabilities,
            "legal_elements": parsed.legal_elements,
            "issues": parsed.issues,
            "query_terms": parsed.query_terms,
        },
        "cards": cards,
        "local_match_notice": local_match_notice,
        "legal_kb_notice": legal_kb_notice,
        "legal_kb_enabled": LEGAL_KB_CLIENT.enabled,
        "legal_kb_status": LEGAL_KB_CLIENT.status(),
        "study_tips": build_study_tips(parsed, cards),
    }


def build_official_search_plan(text: str) -> dict[str, Any]:
    parsed = parse_case_input(text)
    core_terms = parsed.query_terms[:]
    issue_terms = []
    for issue in parsed.issues:
        issue_terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}", issue))

    search_terms = sorted(set(core_terms + issue_terms), key=(core_terms + issue_terms).index)
    if parsed.domain == "外卖配送":
        primary_query = "外卖骑手 送餐途中 撞伤行人 平台责任"
        fallback_queries = [
            "外卖骑手 交通事故 平台承担责任",
            "配送员 执行工作任务 侵权责任 平台",
            "众包骑手 劳务关系 雇主责任 交通事故",
        ]
        wechat_queries = [
            "外卖骑手撞伤行人 平台责任 案例",
            "送餐途中交通事故 平台是否赔偿",
            "众包骑手侵权 平台责任 裁判规则",
        ]
        web_queries = [
            "site:court.gov.cn 外卖骑手 撞伤行人 平台责任",
            "site:chinacourt.org 外卖骑手 交通事故 平台",
            "外卖骑手送餐途中撞伤行人 平台是否承担责任 类案",
        ]
        filters = [
            "优先选择法院官网、参考案例或能回溯到裁判文书的来源。",
            "案由可同时关注机动车交通事故责任纠纷、提供劳务者致害责任纠纷、劳动争议或网络服务平台责任。",
            "结果较多时，加入“执行工作任务”“算法派单”“众包骑手”“平台控制”。",
            "结果较少时，保留“外卖骑手 交通事故 平台责任”作为核心检索式。",
        ]
    elif "餐厅" in text or "餐饮" in text or "自带酒水" in text or "开瓶费" in text:
        primary_query = "餐厅 禁止自带酒水 格式条款 消费者权益"
        fallback_queries = [
            "禁止自带酒水 霸王条款 餐饮服务",
            "餐厅 开瓶费 酒水服务费 合法",
            "店堂告示 消费者选择权 公平交易权",
        ]
        wechat_queries = [
            "禁止自带酒水 格式条款 案例",
            "餐厅自带酒水 开瓶费 法院",
            "餐饮霸王条款 消费者权益 案例",
        ]
        web_queries = [
            "site:court.gov.cn 禁止自带酒水 格式条款",
            "site:chinacourt.org 餐厅 自带酒水 消费者权益",
            "餐厅禁止自带酒水是否合法 类案",
        ]
        filters = [
            "优先选择法院、市场监管、消协或能回溯到裁判文书的来源。",
            "案由优先筛选餐饮服务合同纠纷、消费者权益保护纠纷。",
            "结果较多时，加入“格式条款”“公平交易权”“消费者选择权”。",
            "结果较少时，保留“禁止自带酒水”或“开瓶费”作为核心检索词。",
        ]
    elif "健身房" in text or "会员卡" in text or "预付卡" in text or "闭店" in text:
        primary_query = "健身房 闭店 会员卡 余额 退费"
        fallback_queries = [
            "预付卡 健身房 闭店 返还余额",
            "健身房 私教课 不退费 格式条款",
            "预付式消费 服务合同 解除合同 退费",
        ]
        wechat_queries = [
            "健身房闭店 会员卡余额 法院",
            "预付卡退费 服务合同纠纷 案例",
            "健身房跑路 会员退费 裁判规则",
        ]
        web_queries = [
            "site:court.gov.cn 健身房 闭店 会员卡 退费",
            "site:chinacourt.org 健身房 预付卡 退费",
            "健身房闭店会员卡余额能否追回 类案",
        ]
        filters = [
            "优先选择法院、消协、市场监管或律师整理中能回溯到裁判文书的案例。",
            "案由优先筛选服务合同纠纷、预付式消费纠纷、消费者权益保护纠纷。",
            "结果较多时，在结果中继续检索“闭店”“余额返还”“私教课”“格式条款”。",
            "结果较少时，去掉“突然”等事实词，保留“健身房 预付卡 退费”。",
        ]
    elif "网约车" in text or "误机" in text or "绕路" in text:
        primary_query = "网约车 司机 绕路 误机 平台 赔偿"
        fallback_queries = [
            "网约车 平台责任 运输合同 误机损失",
            "司机绕路 行程延误 可预见损失",
            "网络预约出租汽车 服务合同 赔偿",
        ]
        wechat_queries = [
            "网约车 绕路 误机 赔偿 案例",
            "网约车平台 运输合同 误机损失",
            "司机绕路 行程延误 可预见损失",
        ]
        web_queries = [
            "site:court.gov.cn 网约车 绕路 误机 赔偿",
            "site:chinacourt.org 网约车 平台 赔偿",
            "网约车司机绕路导致误机 类案",
        ]
        filters = [
            "优先选择“参考案例”或法院官网发布案例。",
            "案由优先筛选合同、运输服务、网络服务、消费者权益相关类别。",
            "结果较多时，在结果中继续检索“平台责任”“误机损失”“可预见损失”。",
            "结果较少时，去掉过细事实词，保留“网约车 平台 赔偿”或“运输合同 延误 损失”。",
        ]
    else:
        primary_query = " ".join(search_terms[:8])
        fallback_queries = [
            " ".join(term for term in ["网约车", "绕路", "误机", "平台责任", "运输合同", "违约赔偿"] if term in search_terms or term in text),
            " ".join(term for term in ["平台", "司机", "乘客", "行程延误", "可预见损失"] if term in search_terms or term in text),
            " ".join(parsed.issues[:2]),
        ]
        wechat_queries = [
            f"{primary_query} 案例",
            f"{primary_query} 裁判规则",
            f"{primary_query} 法院",
        ]
        web_queries = [
            f"site:court.gov.cn {primary_query}",
            f"site:chinacourt.org {primary_query}",
            f"{primary_query} 类案",
        ]
        filters = [
            "优先选择“参考案例”、法院官网或能回溯到裁判文书的来源。",
            "先按案由筛选，再按争议焦点和关键事实筛选。",
            "结果较多时，加入责任主体、损害类型、裁判规则等限制词。",
            "结果较少时，删除过细事实，保留行为、主体、责任类型三类核心词。",
        ]
    fallback_queries = [query for query in fallback_queries if query.strip()]

    return {
        "official_url": OFFICIAL_CASE_LIBRARY_URL,
        "primary_query": primary_query or text,
        "fallback_queries": fallback_queries[:3],
        "wechat_queries": wechat_queries[:3],
        "web_queries": web_queries[:3],
        "cause": parsed.cause,
        "issues": parsed.issues,
        "filters": filters,
        "browser_agent_steps": [
            "打开人民法院案例库官网。",
            "将主检索式粘贴到首页检索框并检索。",
            "如果官方库结果太少，改用微信公众号公开检索或普通网页检索中的备用检索式。",
            "记录标题、案号、裁判规则、相似事实和不同事实。",
            "如果页面要求登录、验证码、关注公众号或人工确认，请由用户完成，智能体只继续整理公开可访问结果。",
        ],
        "notice": "该功能不会绕过验证码、登录、关注公众号、付费阅读或网站访问限制；引用案例时应优先核验法院官网、裁判文书或权威发布来源。",
    }


def build_study_tips(parsed: ParsedInput, cards: list[dict[str, Any]]) -> list[str]:
    if not parsed.parse_success:
        return []
    if parsed.domain == "股东知情权":
        return [
            "先核对股东资格、书面查阅请求、送达凭证及请求中载明的目的和资料范围。",
            "公司主张目的不正当，应提交竞争关系、信息滥用风险及可能损害公司利益的具体证据。",
            "应区分可查阅复制的一般公司文件，与会计账簿、会计凭证的法定查阅范围。",
            "法院可通过限定时间、地点、人员及保密措施平衡股东知情权与公司商业秘密。",
        ]
    if parsed.domain == "网络购物":
        return [
            "先固定商品页面、官方正品或全新承诺、订单付款、开箱过程、序列号和双方聊天记录。",
            "手机类商品应核对 IMEI、官网激活结果、保修状态、包装序列号及品牌售后检测材料。",
            "渠道串货不当然等于假货，但若商品无法获得承诺的官方保修、来源或全新状态，仍可能构成不符合约定。",
            "平台是否担责要审查其是否收到多次投诉、是否采取下架处置，以及是否知道或应当知道卖家侵害消费者权益。",
        ]
    if parsed.domain == "离婚房产执行":
        return [
            "先核对离婚协议、登记状态、房款来源、实际占有使用和未过户原因。",
            "离婚协议对双方具有约束力，但能否排除外部债权执行还要审查权利形成时间和受让方过错。",
            "应区分普通金钱债权、以涉案房产为交易基础形成的债权及设有担保物权的债权。",
            "债务是否属于夫妻共同债务需要结合共同签名、家庭生活或共同经营受益等证据单独判断。",
        ]
    if parsed.domain == "物业公共收益":
        return [
            "先证明广告位属于业主共有部分，并取得广告合同、收款流水和公共收益台账。",
            "业委会起诉前应核对备案情况、任期及业主大会授权或管理规约依据。",
            "公共收益应先扣除合理成本；物业公司需说明收入、支出和维修用途，不能只作概括陈述。",
            "对三年收入和维修支出有争议时，可申请审计、调查令或责令物业提交账簿资料。",
        ]
    if parsed.domain == "相邻关系":
        return [
            "先固定空调外机位置、与卧室窗户的距离，并保存照片、视频和物业沟通记录。",
            "噪声、振动和滴水侵扰宜通过持续录音录像、检测报告或现场勘验证明。",
            "是否有统一外机位不是唯一标准，仍需判断实际安装是否超过相邻住户合理容忍限度。",
            "精神损害赔偿需要证明侵扰达到较严重程度；排除妨害、移机或整改通常是更核心的请求。",
        ]
    if parsed.domain == "工业品买卖":
        return [
            "先核对合同技术规格、样品确认、交付单、验收记录及付款节点。",
            "质量争议应尽量通过封样、检测报告、退货实物和双方沟通记录固定证据。",
            "买方未及时提出质量异议可能影响抗辩，但隐蔽瑕疵仍需结合发现时间和检验条件判断。",
            "下游退货损失应证明实际发生、与涉案产品缺陷存在因果关系，并属于订约时可预见范围。",
        ]
    if parsed.domain == "商铺租赁":
        return [
            "先核对租赁期限、租金支付节点、押金用途、解除条件和违约金条款。",
            "商圈客流下降通常属于商业经营风险；主张情势变更还需证明变化重大、不可预见且继续履行明显不公平。",
            "承租人搬离后仍应固定交还钥匙、通知解除和出租人接收房屋的时间，以判断租金计算截止日。",
            "违约金、押金抵扣和空置损失应避免重复计算，过高违约金可以请求依法调整。",
        ]
    if parsed.domain == "道路交通事故":
        return [
            "先核对交通事故责任认定书、现场监控、行车记录仪和人行横道信号状态。",
            "机动车经过人行横道时的减速、停车让行义务，与行人是否存在过错应分别判断。",
            "医疗费、误工费等损失应逐项提供病历、票据、收入及误工期限证明。",
            "精神损害抚慰金通常结合伤残或严重损害后果、双方过错和当地裁判尺度确定。",
        ]
    if parsed.domain == "民间借贷":
        return [
            "先核对借条、转账记录、现金交付凭证和双方聊天记录，证明实际借款本金。",
            "利息是否受支持，需要结合借款成立时间、约定方式和司法保护范围判断。",
            "已经支付的款项要区分本金、利息及其他费用，并核对是否需要重新抵扣。",
            "逾期利息、违约金、服务费等合计负担应一并审查，不能只看合同中的利率名称。",
        ]
    if parsed.domain == "房屋租赁":
        return [
            "先核对租赁合同、押金支付凭证、退租时间和房屋交接记录。",
            "出租人主张扣除押金时，应说明合同依据、具体损坏事实和实际支出。",
            "重点区分正常使用形成的自然损耗与承租人不当使用造成的损坏。",
            "证据可围绕入住和退租照片、验收记录、维修票据及双方聊天记录组织。",
        ]
    if parsed.domain == "劳动争议":
        return [
            "先确认劳动关系、工作期限、工资标准和争议行为发生时间。",
            "重点核对劳动合同、工资流水、考勤记录、规章制度及解除通知。",
            "用人单位作出解除或扣减工资等处理时，通常需要证明事实和制度依据。",
            "补偿或赔偿金额应结合工资基数、工作年限和具体请求逐项计算。",
        ]
    if parsed.domain == "教育培训":
        return [
            "先核对培训合同、付款记录、已上和剩余课时。",
            "判断机构是否还能按约提供同等课程，以及合同目的是否已经无法实现。",
            "不退费条款需要结合提示说明义务和是否排除消费者主要权利判断。",
            "退费金额应以实际履行情况为基础，避免直接套用机构单方制定的折算标准。",
        ]
    if parsed.domain == "医疗美容":
        return [
            "先区分服务效果争议、误导宣传争议和医疗损害争议。",
            "重点核对术前告知、风险提示、宣传材料、合同、病历和收费凭证。",
            "涉及人身损害时，需要进一步证明诊疗过错、损害后果和因果关系。",
            "宣传中的明确效果承诺可能影响合同内容、欺诈或违约责任的判断。",
        ]
    if parsed.domain == "宠物服务":
        return [
            "先确认双方关系更接近保管合同还是宠物服务合同。",
            "重点核对寄养协议、交接记录、宠物健康和身份信息、门店看护规则。",
            "判断店家责任时，要看是否尽到围挡、看护、出入管理和及时寻找通知义务。",
            "损失证明可围绕购买或领养凭证、治疗和寻找费用、聊天记录及报警或寻宠记录组织。",
        ]
    if parsed.domain == "外卖配送":
        return [
            "先区分交通事故基础责任和平台是否承担替代责任两个层次。",
            "重点核对骑手是否处于接单、取餐、送餐途中，以及事故是否发生在履职过程中。",
            "判断平台责任时，要看平台是否派单、计价、考核、处罚、装备管理或对路线时效进行控制。",
            "证据上优先收集事故认定书、订单记录、配送轨迹、平台规则、骑手身份关系和伤情损失凭证。",
        ]
    if any(term in parsed.raw for term in ["餐厅", "餐饮", "自带酒水", "开瓶费"]):
        return [
            "先判断规则是协商条款还是餐厅单方设置的格式条款。",
            "重点比较该规则是否排除消费者自主选择权，或变相强制购买店内酒水。",
            "如果餐厅收取开瓶费，要进一步看是否事先明示、金额是否合理、是否对应实际服务。",
            "检索时同时使用“禁止自带酒水”“格式条款”“公平交易权”“消费者选择权”。",
        ]
    if any(term in parsed.raw for term in ["健身房", "会员卡", "预付卡", "闭店"]):
        return [
            "先确认合同主体、付款记录、剩余余额或剩余课时，再检索退费规则。",
            "重点比较闭店是否导致合同目的无法实现，以及经营者是否提供等价替代服务。",
            "遇到“不退费”条款，要分析是否属于格式条款以及是否排除消费者主要权利。",
            "同时收集门店公告、聊天记录、付款凭证和闭店现场证据，方便论证返还范围。",
        ]
    if any(term in parsed.raw for term in ["网约车", "误机", "绕路"]):
        return [
            "先区分司机绕路、平台派单、乘客自身安排三类原因。",
            "误机损失要重点证明可预见性、因果关系和实际损失金额。",
            "检索时同时保留支持平台责任和限制赔偿范围的案例。",
        ]
    tips = [
        "先用争议焦点检索，再用事实要素筛选，避免只搜零散关键词。",
        "比较主体关系、行为性质、违约或过错、损失与因果关系等核心事实。",
        "同时保留支持与不支持责任的案例，便于检验请求基础和抗辩边界。",
    ]
    if "连带责任" in parsed.query_terms:
        tips.append("论证连带责任时，要特别补强共同宣传、共同获利或明知应知的证据。")
    if cards and "主播" in cards[0]["support_for"]:
        tips.append("首位案例偏向主播抗辩，可作为区分不利案例的训练素材。")
    return tips[:4]


def answer_question(question: str, context: str) -> dict[str, str]:
    merged = question + " " + context
    for key, answer in QUESTION_BANK.items():
        if key in merged:
            return {"answer": answer}
    return {
        "answer": "可以按“行为性质、主体过错、因果关系、责任范围”四步分析。先判断宣传是否足以误导消费者，再看主播或平台是否实际参与、是否获利、是否能核验，最后比较类案中的裁判要旨是否支持你的立场。"
    }


def export_markdown(payload: dict[str, Any]) -> str:
    result = search_cases(payload.get("query", ""))
    lines = ["# 类案检索速配报告", ""]
    lines.append(f"检索问题：{payload.get('query', '')}")
    lines.append(f"建议案由：{result['parsed']['cause']}")
    lines.append("")
    lines.append("## 争议焦点")
    for issue in result["parsed"]["issues"]:
        lines.append(f"- {issue}")
    lines.append("")
    lines.append("## Top 3 类案卡片")
    for idx, card in enumerate(result["cards"], 1):
        lines.append(f"### {idx}. {card['title']}")
        lines.append(f"- 案号：{card['docket']}")
        lines.append(f"- 法院/日期：{card['court']}，{card['date']}")
        lines.append(f"- 匹配度：{card['score']}%")
        lines.append(f"- 裁判要旨：{card['holding']}")
        lines.append(f"- 可借鉴角度：{card['angle']}")
        lines.append("- 学习型摘要：")
        for sentence in card["summary"]:
            lines.append(f"  - {sentence}")
        lines.append("")
    return "\n".join(lines)



def auth_cookie_value() -> str:
    if not APP_PASSWORD:
        return ""
    return hashlib.sha256(APP_PASSWORD.encode("utf-8")).hexdigest()


def login_page(error: str = "") -> str:
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>访问验证 - 类案检索速配智能体</title>
  <style>
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f7fb; color: #1f2a37; }}
    form {{ width: min(420px, calc(100vw - 32px)); background: #fff; border: 1px solid #dce4ee; border-radius: 8px; padding: 24px; box-shadow: 0 16px 45px rgba(31, 42, 55, .12); }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    p {{ margin: 0 0 18px; color: #607086; line-height: 1.6; }}
    label {{ display: block; margin: 0 0 8px; font-weight: 650; }}
    input {{ width: 100%; box-sizing: border-box; min-height: 42px; border: 1px solid #bfccda; border-radius: 8px; padding: 0 12px; font: inherit; }}
    button {{ width: 100%; margin-top: 14px; min-height: 42px; border: 0; border-radius: 8px; background: #235c95; color: #fff; font: inherit; font-weight: 700; cursor: pointer; }}
    .error {{ color: #a43434; background: #fff2f2; border: 1px solid #f0c4c4; padding: 10px; border-radius: 8px; }}
  </style>
</head>
<body>
  <form method="post" action="/login">
    <h1>访问验证</h1>
    <p>请输入访问密码后继续使用智能体。</p>
    {error_html}
    <label for="password">访问密码</label>
    <input id="password" name="password" type="password" autocomplete="current-password" autofocus />
    <button type="submit">进入</button>
  </form>
</body>
</html>"""

INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>类案检索速配智能体</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #172033;
      --muted: #5d6a7c;
      --line: #d9e0ea;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --accent: #1d6f8f;
      --accent-2: #8a4f1d;
      --soft: #eaf5f7;
      --good: #28724f;
      --warn: #ad5a11;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    header {
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      padding: 18px clamp(18px, 5vw, 52px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }
    h1 { margin: 0; font-size: clamp(22px, 3vw, 32px); letter-spacing: 0; }
    header p { margin: 4px 0 0; color: var(--muted); font-size: 14px; }
    main {
      width: min(1280px, 100%);
      margin: 0 auto;
      padding: 22px clamp(14px, 3vw, 34px) 40px;
      display: grid;
      grid-template-columns: minmax(320px, 430px) 1fr;
      gap: 18px;
    }
    section, aside, .card, dialog {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .input-panel { padding: 18px; align-self: start; position: sticky; top: 14px; }
    label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 8px; }
    textarea {
      width: 100%;
      min-height: 168px;
      resize: vertical;
      border: 1px solid #c8d3df;
      border-radius: 8px;
      padding: 12px;
      font: inherit;
      line-height: 1.55;
      color: var(--ink);
      background: #fbfcfe;
    }
    .button-row { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
    button {
      border: 1px solid transparent;
      border-radius: 7px;
      min-height: 38px;
      padding: 0 14px;
      font: inherit;
      cursor: pointer;
      background: #edf2f7;
      color: var(--ink);
    }
    button.primary { background: var(--accent); color: white; }
    button.ghost { border-color: var(--line); background: white; }
    button:focus-visible, textarea:focus, input:focus { outline: 3px solid #c8e6ef; outline-offset: 1px; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .chip {
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 3px 9px;
      border-radius: 999px;
      background: var(--soft);
      color: #155467;
      font-size: 12px;
      border: 1px solid #c8e3e9;
    }
    .workspace { display: grid; gap: 14px; }
    .analysis-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .mini { padding: 14px; }
    .mini h2, .results h2, .qa h2 { margin: 0 0 10px; font-size: 17px; }
    .mini dl { margin: 0; display: grid; gap: 8px; }
    .mini dt { color: var(--muted); font-size: 12px; }
    .mini dd { margin: 2px 0 0; line-height: 1.5; }
    .results { padding: 16px; }
    .cards { display: grid; gap: 12px; }
    .case-card { padding: 15px; }
    .case-head {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: start;
    }
    .case-card h3 { margin: 0; font-size: 18px; line-height: 1.35; }
    .meta { margin-top: 5px; color: var(--muted); font-size: 13px; line-height: 1.5; }
    .score {
      width: 64px;
      height: 64px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: #f2f7e9;
      color: var(--good);
      border: 1px solid #d5e7bd;
      font-weight: 700;
    }
    .two-col { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
    .note { background: #fbfcfe; border: 1px solid #e3e8ef; border-radius: 8px; padding: 10px; line-height: 1.55; }
    .note b { color: var(--accent-2); }
    details { margin-top: 10px; }
    summary { cursor: pointer; color: var(--accent); font-weight: 650; }
    ul { padding-left: 19px; margin: 8px 0; }
    li { margin: 5px 0; line-height: 1.55; }
    mark { background: #fff1b8; padding: 0 2px; border-radius: 3px; }
    .qa { padding: 16px; display: grid; gap: 10px; }
    .qa-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; }
    input {
      min-height: 38px;
      border: 1px solid #c8d3df;
      border-radius: 8px;
      padding: 0 12px;
      font: inherit;
    }
    .answer { min-height: 44px; color: var(--ink); line-height: 1.6; background: #fbfcfe; border: 1px solid #e3e8ef; border-radius: 8px; padding: 10px; }
    .empty {
      border: 1px dashed #b9c5d3;
      background: #ffffff;
      color: var(--muted);
      border-radius: 8px;
      padding: 32px;
      text-align: center;
      line-height: 1.7;
    }
    @media (max-width: 920px) {
      main { grid-template-columns: 1fr; }
      .input-panel { position: static; }
    }
    @media (max-width: 640px) {
      header { align-items: flex-start; flex-direction: column; }
      .analysis-grid, .two-col, .qa-row { grid-template-columns: 1fr; }
      .case-head { grid-template-columns: 1fr; }
      .score { width: auto; height: 38px; border-radius: 8px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>类案检索速配智能体</h1>
      <p>把自然语言案情转换为争议焦点、法律要素和 Top 3 学习型类案卡片。内置数据为教学示例。</p>
    </div>
    <div class="button-row"><span class="chip" id="kbStatus">知识库状态检测中</span><button class="ghost" id="loadExample">填入示例</button></div>
  </header>
  <main>
    <aside class="input-panel">
      <label for="caseInput">输入案情或检索问题</label>
      <textarea id="caseInput">直播带货虚假宣传，主播是否承担连带责任？消费者因主播推荐购买保健品，后来发现功效宣传不实，主播收取佣金但称自己只是介绍商品。</textarea>
      <div class="button-row">
        <button class="primary" id="searchBtn">速配类案</button>
        <button id="exportBtn">导出报告</button>
      </div>
      <div class="chips" id="quickChips">
        <span class="chip">虚假宣传</span>
        <span class="chip">主播责任</span>
        <span class="chip">连带责任</span>
        <span class="chip">明知应知</span>
      </div>
    </aside>
    <div class="workspace">
      <div id="analysis" class="empty">点击“速配类案”后，这里会显示案由、法律要素、争议焦点和检索关键词。</div>
      <section class="results">
        <h2>Top 3 类案卡片</h2>
        <div id="kbNotice" class="meta"></div>
        <div id="cards" class="cards">
          <div class="empty">暂无结果。</div>
        </div>
      </section>
      <section class="qa">
        <h2>多源案例检索 Agent</h2>
        <div class="button-row">
          <button id="officialPlanBtn">生成多源检索方案</button>
          <button class="ghost" id="officialOpenBtn">打开人民法院案例库</button>
          <button class="ghost" id="weixinOpenBtn">打开微信公开检索</button>
        </div>
        <div id="officialPlan" class="answer">用于把当前案情转换成法院库、微信公众号公开内容和网页检索式。遇到登录、验证码、关注或付费限制时，请人工接管。</div>
      </section>
      <section class="qa">
        <h2>智能问答与模拟法庭辅助</h2>
        <div class="qa-row">
          <input id="question" placeholder="例如：为什么主播需要承担责任？或：我代表消费者如何论证？" />
          <button id="askBtn">提问</button>
        </div>
        <div id="answer" class="answer">检索后可围绕判例摘要继续追问。</div>
      </section>
    </div>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    let lastResult = null;

    const safe = (text) => String(text ?? "").replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));

    const highlight = (text, terms = []) => {
      let escaped = String(text).replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
      terms.filter(Boolean).sort((a, b) => b.length - a.length).slice(0, 12).forEach((term) => {
        const safe = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        escaped = escaped.replace(new RegExp(safe, "g"), `<mark>${term}</mark>`);
      });
      return escaped;
    };

    async function runSearch() {
      const query = $("caseInput").value.trim();
      if (!query) return;
      $("cards").innerHTML = '<div class="empty">正在解析案情并匹配类案...</div>';
      const res = await fetch("/api/search", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query})
      });
      lastResult = await res.json();
      renderKnowledgeBaseStatus(lastResult.legal_kb_status);
      $("kbNotice").textContent = lastResult.legal_kb_notice || "";
      if (!lastResult.cards.length) {
        const planRes = await fetch("/api/official-plan", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({query})
        });
        lastResult.externalPlan = await planRes.json();
      }
      renderAnalysis(lastResult.parsed);
      renderCards(lastResult.cards, lastResult.parsed.query_terms);
    }

    function renderKnowledgeBaseStatus(status) {
      const node = $("kbStatus");
      if (!node || !status) return;
      node.textContent = status.enabled ? `AI 案情理解：已启用（${status.model}）` : "AI 案情理解：本地规则模式";
      node.style.background = status.enabled ? "#e8f6ee" : "#fff4df";
      node.style.color = status.enabled ? "#28724f" : "#8a4f1d";
    }

    function renderAnalysis(parsed) {
      if (!parsed.success) {
        $("analysis").className = "empty";
        $("analysis").innerHTML = `
          <b>案情解析失败</b>
          <div style="margin-top:8px">${safe(parsed.notice || "当前案例库无法可靠识别该案情，已停止生成案由和争议焦点，避免误导。")}</div>
        `;
        return;
      }
      const legal = parsed.legal_elements;
      $("analysis").className = "analysis-grid";
      $("analysis").innerHTML = `
        <section class="mini">
          <h2>案情解析</h2>
          <dl>
            <div><dt>建议案由</dt><dd>${safe(parsed.cause)}</dd></div>
            <div><dt>领域</dt><dd>${safe(parsed.domain || "通用")}</dd></div>
            <div><dt>行为</dt><dd>${safe((parsed.behaviors.length ? parsed.behaviors : ["网络交易宣传"]).join("、"))}</dd></div>
            <div><dt>主体</dt><dd>${safe((parsed.subjects.length ? parsed.subjects : ["经营者", "推广者"]).join("、"))}</dd></div>
            <div><dt>责任类型</dt><dd>${safe((parsed.liabilities.length ? parsed.liabilities : ["赔偿责任"]).join("、"))}</dd></div>
          </dl>
        </section>
        <section class="mini">
          <h2>争议焦点</h2>
          <ul>${parsed.issues.map((item) => `<li>${safe(item)}</li>`).join("")}</ul>
          <div class="chips">${parsed.query_terms.slice(0, 12).map((item) => `<span class="chip">${safe(item)}</span>`).join("")}</div>
        </section>
        <section class="mini">
          <h2>法律要素</h2>
          <dl>${Object.entries(legal).map(([key, val]) => `<div><dt>${safe(key)}</dt><dd>${safe(val.join("、"))}</dd></div>`).join("")}</dl>
        </section>
        <section class="mini">
          <h2>学习提示</h2>
          <ul>${lastResult.study_tips.map((item) => `<li>${safe(item)}</li>`).join("")}</ul>
        </section>
      `;
    }

    function renderCards(cards, terms) {
      if (!cards.length) {
        renderExternalSearchCards(lastResult.externalPlan, lastResult.local_match_notice);
        return;
      }
      $("cards").innerHTML = cards.map((card, index) => `
        <article class="case-card card">
          <div class="case-head">
            <div>
              <h3>${index + 1}. ${safe(card.title)}</h3>
              <div class="meta">${safe(card.docket)} · ${safe(card.court)} · ${safe(card.date)} · ${safe(card.cause)} · ${safe(card.domain || "通用")}</div>
              <div class="meta">来源：${safe(card.source || "本地案例库")}</div>
            </div>
            <div class="score">${card.score}%</div>
          </div>
          <div class="two-col">
            <div class="note"><b>相似点</b><ul>${card.similarities.map((item) => `<li>${highlight(item, terms)}</li>`).join("")}</ul></div>
            <div class="note"><b>差异点</b><ul>${card.differences.map((item) => `<li>${highlight(item, terms)}</li>`).join("")}</ul></div>
          </div>
          <p class="note"><b>裁判要旨：</b>${highlight(card.holding, terms)}</p>
          <p class="note"><b>可借鉴角度：</b>${safe(card.angle)}</p>
          <details>
            <summary>展开学习型摘要</summary>
            <ul>${card.summary.map((item) => `<li>${highlight(item, terms)}</li>`).join("")}</ul>
          </details>
        </article>
      `).join("");
    }

    function renderExternalSearchCards(plan, notice) {
      if (!plan) {
        $("cards").innerHTML = `<div class="empty">${notice || "暂无足够相近的本地类案。"}</div>`;
        return;
      }
      const cards = [
        {
          title: "人民法院案例库",
          source: "最高人民法院官方案例库",
          query: plan.primary_query,
          detail: "优先核验权威案例。若结果较少，使用备用检索式缩放关键词。",
          button: "打开官方库",
          url: plan.official_url
        },
        {
          title: "微信公众号公开内容",
          source: "公开文章线索",
          query: (plan.wechat_queries || []).join("；") || plan.primary_query,
          detail: "适合找法院公众号、律所文章、消协案例线索，引用前需回到权威来源核验。",
          button: "打开微信检索",
          url: "https://weixin.sogou.com/"
        },
        {
          title: "网页与法院官网检索",
          source: "法院官网/中国法院网/公开网页",
          query: (plan.web_queries || []).join("；") || plan.primary_query,
          detail: "用 site:court.gov.cn、site:chinacourt.org 等限定来源，减少泛网页噪音。",
          button: "打开网页检索",
          url: `https://www.baidu.com/s?wd=${encodeURIComponent((plan.web_queries || [plan.primary_query])[0])}`
        }
      ];
      $("cards").innerHTML = `
        <div class="empty">${notice || "本地案例库暂未找到足够相近的类案。"}</div>
        ${cards.map((card, index) => `
          <article class="case-card card">
            <div class="case-head">
              <div>
                <h3>${index + 1}. ${safe(card.title)}</h3>
                <div class="meta">来源：${card.source}</div>
              </div>
              <div class="score">检索</div>
            </div>
            <p class="note"><b>建议检索式：</b>${card.query}</p>
            <p class="note"><b>使用方式：</b>${card.detail}</p>
            <details open>
              <summary>筛选步骤</summary>
              <ul>${plan.filters.map((item) => `<li>${safe(item)}</li>`).join("")}</ul>
            </details>
            <div class="button-row">
              <button class="primary" type="button" onclick="window.open('${card.url}', '_blank', 'noopener,noreferrer')">${card.button}</button>
            </div>
          </article>
        `).join("")}
      `;
    }

    async function ask() {
      const question = $("question").value.trim();
      if (!question) return;
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question, context: JSON.stringify(lastResult || {})})
      });
      const data = await res.json();
      $("answer").textContent = data.answer;
    }

    async function exportReport() {
      const query = $("caseInput").value.trim();
      if (!query) return;
      const res = await fetch("/api/export", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query})
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "类案检索速配报告.md";
      a.click();
      URL.revokeObjectURL(url);
    }

    async function officialPlan() {
      const query = $("caseInput").value.trim();
      if (!query) return;
      const res = await fetch("/api/official-plan", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({query})
      });
      const data = await res.json();
      $("officialPlan").innerHTML = `
        <p><b>建议案由：</b>${data.cause}</p>
        <p><b>主检索式：</b>${data.primary_query}</p>
        <p><b>备用检索式：</b>${data.fallback_queries.join("；") || "暂无"}</p>
        <p><b>微信公众号检索式：</b>${data.wechat_queries.join("；") || "暂无"}</p>
        <p><b>网页检索式：</b>${data.web_queries.join("；") || "暂无"}</p>
        <p><b>争议焦点：</b></p>
        <ul>${data.issues.map((item) => `<li>${safe(item)}</li>`).join("")}</ul>
        <p><b>筛选步骤：</b></p>
        <ul>${data.filters.map((item) => `<li>${safe(item)}</li>`).join("")}</ul>
        <p><b>浏览器 Agent 步骤：</b></p>
        <ul>${data.browser_agent_steps.map((item) => `<li>${safe(item)}</li>`).join("")}</ul>
        <p>${data.notice}</p>
      `;
    }

    function openOfficialLibrary() {
      window.open("http://rmfyalk.court.gov.cn", "_blank", "noopener,noreferrer");
    }

    function openWeixinSearch() {
      window.open("https://weixin.sogou.com/", "_blank", "noopener,noreferrer");
    }

    $("searchBtn").addEventListener("click", runSearch);
    $("askBtn").addEventListener("click", ask);
    $("exportBtn").addEventListener("click", exportReport);
    $("officialPlanBtn").addEventListener("click", officialPlan);
    $("officialOpenBtn").addEventListener("click", openOfficialLibrary);
    $("weixinOpenBtn").addEventListener("click", openWeixinSearch);
    $("loadExample").addEventListener("click", () => {
      $("caseInput").value = "我代表消费者，想主张主播承担责任。直播间宣传某珠宝为天然高等级材质，消费者因主播保真承诺购买，鉴定后发现等级不符。主播收取佣金，商家称责任只在店铺。";
      runSearch();
    });
    runSearch();
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str, extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self._send(302, b"", "text/plain; charset=utf-8", {"Location": location})

    def _authenticated(self) -> bool:
        if not APP_PASSWORD:
            return True
        expected = auth_cookie_value()
        cookies = self.headers.get("Cookie", "")
        for part in cookies.split(";"):
            name, _, value = part.strip().partition("=")
            if name == AUTH_COOKIE_NAME and hmac.compare_digest(value, expected):
                return True
        return False

    def _require_auth(self) -> bool:
        if self._authenticated():
            return True
        if self.path.startswith("/api/"):
            self._json({"error": "unauthorized"}, 401)
        else:
            self._redirect("/login")
        return False

    def _json(self, data: Any, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/login":
            if self._authenticated():
                self._redirect("/")
            else:
                self._send(200, login_page().encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        if path == "/api/status":
            self._json({"legal_kb": LEGAL_KB_CLIENT.status(), "local_cases": len(CASES), "password_enabled": bool(APP_PASSWORD)})
            return
        if not self._require_auth():
            return

        if path in ["/", "/index.html"]:
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {key: value[0] for key, value in parse_qs(raw).items()}

        path = urlparse(self.path).path
        if path == "/login":
            password = str(payload.get("password", ""))
            if APP_PASSWORD and hmac.compare_digest(password, APP_PASSWORD):
                self._send(302, b"", "text/plain; charset=utf-8", {
                    "Location": "/",
                    "Set-Cookie": f"{AUTH_COOKIE_NAME}={auth_cookie_value()}; Path=/; HttpOnly; SameSite=Lax"
                })
            else:
                self._send(403, login_page("密码不正确，请重试。 ").encode("utf-8"), "text/html; charset=utf-8")
            return
        if not self._require_auth():
            return

        if path == "/api/search":
            query = str(payload.get("query", "")).strip()
            self._json(search_cases(query))
        elif path == "/api/official-plan":
            query = str(payload.get("query", "")).strip()
            self._json(build_official_search_plan(query))
        elif path == "/api/ask":
            self._json(answer_question(str(payload.get("question", "")), str(payload.get("context", ""))))
        elif path == "/api/export":
            content = export_markdown(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="case_match_report.md"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"类案检索速配智能体已启动：http://127.0.0.1:{PORT}")
    print(f"同一局域网设备可使用本机 IP 访问，例如：http://你的电脑IP:{PORT}")
    print(f"法律知识库状态：{LEGAL_KB_CLIENT.status()['message']}")
    print(f"访问密码：{'已启用' if APP_PASSWORD else '未启用（设置 APP_PASSWORD 可开启）'}")
    print("按 Ctrl+C 停止服务。")
    server.serve_forever()


if __name__ == "__main__":
    main()
