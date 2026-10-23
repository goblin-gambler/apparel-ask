"""
服装连锁数仓模拟数据生成脚本

按固定随机种子生成 2024 全年服装零售数据，写入 dw 库
维表数据量小，事实表数据量大，统一在一个脚本里生成，保证订单、退货和库存的口径一致

用法：
    uv run python -m app.scripts.seed_apparel_dw
"""

import asyncio
import calendar
import random
from datetime import date, datetime, timedelta

import asyncmy

from app.conf.app_config import app_config

# 固定种子，保证每次重建得到同一份数据，便于复现实验结果
SEED = 20240101
START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 12, 31)

REGIONS = [
    ("R001", "上海市", "上海", "一线", "华东"),
    ("R002", "浙江省", "杭州", "新一线", "华东"),
    ("R003", "浙江省", "宁波", "二线", "华东"),
    ("R004", "浙江省", "温州", "二线", "华东"),
    ("R005", "浙江省", "台州", "三线", "华东"),
    ("R006", "江苏省", "苏州", "新一线", "华东"),
    ("R007", "江苏省", "南京", "新一线", "华东"),
    ("R008", "安徽省", "合肥", "二线", "华东"),
    ("R009", "广东省", "广州", "一线", "华南"),
    ("R010", "广东省", "深圳", "一线", "华南"),
    ("R011", "广东省", "东莞", "新一线", "华南"),
    ("R012", "广东省", "佛山", "二线", "华南"),
    ("R013", "福建省", "福州", "二线", "华南"),
    ("R014", "福建省", "厦门", "二线", "华南"),
    ("R015", "福建省", "泉州", "二线", "华南"),
    ("R016", "广西壮族自治区", "南宁", "二线", "华南"),
    ("R017", "湖北省", "武汉", "新一线", "华中"),
    ("R018", "湖南省", "长沙", "新一线", "华中"),
    ("R019", "江西省", "南昌", "二线", "华中"),
    ("R020", "河南省", "郑州", "新一线", "华中"),
    ("R021", "四川省", "成都", "新一线", "西南"),
    ("R022", "重庆市", "重庆", "一线", "西南"),
    ("R023", "云南省", "昆明", "二线", "西南"),
    ("R024", "贵州省", "贵阳", "二线", "西南"),
    ("R025", "北京市", "北京", "一线", "华北"),
    ("R026", "天津市", "天津", "二线", "华北"),
    ("R027", "山东省", "济南", "二线", "华北"),
    ("R028", "河北省", "石家庄", "二线", "华北"),
]

# 城市 -> 门店数量。门店集中在华东、华南，其他区域少量布点
STORE_PLAN = {
    "杭州": 5,
    "上海": 4,
    "宁波": 3,
    "温州": 2,
    "台州": 3,
    "苏州": 2,
    "南京": 2,
    "合肥": 1,
    "广州": 3,
    "深圳": 3,
    "东莞": 2,
    "佛山": 2,
    "福州": 2,
    "厦门": 1,
    "泉州": 1,
    "武汉": 2,
    "长沙": 2,
    "南昌": 1,
    "郑州": 1,
    "成都": 2,
    "重庆": 1,
    "昆明": 1,
    "北京": 2,
    "天津": 1,
    "济南": 1,
}

AREAS = {
    "杭州": ["西湖银泰", "滨江宝龙", "武林广场", "钱江新城", "城西银泰"],
    "上海": ["静安久光", "人民广场", "徐家汇", "五角场"],
    "宁波": ["天一广场", "鄞州万达", "东部银泰"],
    "温州": ["五马街", "瓯海万象城"],
    "台州": ["椒江万达", "黄岩吾悦", "温岭银泰"],
    "苏州": ["观前街", "园区久光"],
    "南京": ["新街口", "江宁万达"],
    "合肥": ["之心城"],
    "广州": ["天河城", "北京路", "番禺万博"],
    "深圳": ["海岸城", "华强北", "龙岗万科"],
    "东莞": ["南城鸿福路", "松山湖"],
    "佛山": ["祖庙", "南海万达"],
    "福州": ["东街口", "仓山万达"],
    "厦门": ["中山路"],
    "泉州": ["丰泽浦西"],
    "武汉": ["江汉路", "光谷世界城"],
    "长沙": ["五一广场", "梅溪湖"],
    "南昌": ["八一广场"],
    "郑州": ["二七广场"],
    "成都": ["春熙路", "太古里"],
    "重庆": ["解放碑"],
    "昆明": ["南屏街"],
    "北京": ["三里屯", "西单"],
    "天津": ["滨江道"],
    "济南": ["泉城路"],
}

# 每个品类的款数、尺码、颜色、款式、形容词、产品线和价格区间
CATEGORY_SPECS = {
    "女装": {
        "count": 120,
        "sizes": ["S", "M", "L", "XL"],
        "colors": ["米白", "燕麦", "藏青", "黑色", "焦糖", "雾霾蓝", "酒红", "浅灰"],
        "types": [
            "针织开衫", "衬衫", "连衣裙", "半身裙", "西装外套", "风衣",
            "羽绒服", "毛衣", "阔腿裤", "牛仔外套", "T恤", "卫衣",
        ],
        "adjs": ["轻暖", "修身", "宽松", "高腰", "复古", "简约", "法式", "通勤", "软糯", "垂感"],
        "series": ["通勤", "休闲", "基础", "度假"],
        "price_range": (199, 899),
        "cost_ratio": (0.22, 0.36),
    },
    "男装": {
        "count": 80,
        "sizes": ["M", "L", "XL", "XXL"],
        "colors": ["黑色", "藏青", "深灰", "卡其", "军绿", "白色", "棕色", "浅蓝"],
        "types": [
            "夹克", "衬衫", "卫衣", "休闲裤", "针织衫", "羽绒服",
            "大衣", "POLO衫", "短袖T恤", "工装裤",
        ],
        "adjs": ["轻量", "修身", "宽松", "复古", "简约", "商务", "休闲", "加厚", "防风", "基础"],
        "series": ["通勤", "休闲", "户外", "基础"],
        "price_range": (199, 999),
        "cost_ratio": (0.24, 0.38),
    },
    "童装": {
        "count": 50,
        "sizes": ["110", "120", "130", "140", "150"],
        "colors": ["粉色", "天蓝", "鹅黄", "白色", "藏青", "红色"],
        "types": ["卫衣", "连衣裙", "运动套装", "牛仔裤", "羽绒服", "针织衫", "T恤", "短裤"],
        "adjs": ["萌趣", "柔软", "宽松", "保暖", "轻便", "卡通", "活力", "基础"],
        "series": ["童趣", "运动", "基础"],
        "price_range": (99, 499),
        "cost_ratio": (0.25, 0.40),
    },
    "鞋履": {
        "count": 30,
        "sizes": ["36", "37", "38", "39", "40", "41", "42", "43"],
        "colors": ["黑色", "白色", "米色", "棕色", "灰色"],
        "types": ["运动鞋", "板鞋", "乐福鞋", "短靴", "凉鞋", "帆布鞋", "老爹鞋", "马丁靴"],
        "adjs": ["轻便", "舒适", "复古", "简约", "厚底", "百搭", "软底", "透气"],
        "series": ["休闲", "运动", "通勤"],
        "price_range": (299, 899),
        "cost_ratio": (0.28, 0.42),
    },
    "配饰": {
        "count": 20,
        "sizes": ["均码"],
        "colors": ["黑色", "米色", "棕色", "灰色", "酒红"],
        "types": ["针织围巾", "棒球帽", "皮带", "托特包", "双肩包", "手套", "袜子", "丝巾"],
        "adjs": ["简约", "复古", "百搭", "轻便", "柔软", "通勤"],
        "series": ["通勤", "休闲", "基础"],
        "price_range": (59, 299),
        "cost_ratio": (0.30, 0.45),
    },
}

CHANNELS = [
    ("CH01", "门店POS", "线下", "门店", 55),
    ("CH02", "微信小程序", "线上", "微信", 18),
    ("CH03", "第三方电商", "线上", "电商平台", 12),
    ("CH04", "直播电商", "线上", "直播平台", 8),
    ("CH05", "导购私域", "私域", "企业微信", 7),
]

# (activity_id, 名称, 类型, 开始, 结束, 折扣率, 门槛, 减免)
PROMOTIONS = [
    ("PR001", "元旦满减", "满减", "2024-01-01", "2024-01-03", None, 599.00, 80.00),
    ("PR002", "春节会员日", "会员日", "2024-02-08", "2024-02-14", 0.88, None, None),
    ("PR003", "春季上新", "折扣", "2024-03-01", "2024-03-31", 0.90, None, None),
    ("PR004", "五一满减", "满减", "2024-05-01", "2024-05-05", None, 499.00, 50.00),
    ("PR005", "618 大促", "折扣", "2024-06-01", "2024-06-18", 0.80, None, None),
    ("PR006", "夏季清仓", "季末清仓", "2024-07-01", "2024-07-31", 0.60, None, None),
    ("PR007", "秋季会员日", "会员日", "2024-09-01", "2024-09-10", 0.88, None, None),
    ("PR008", "国庆满减", "满减", "2024-10-01", "2024-10-07", None, 699.00, 100.00),
    ("PR009", "双11 大促", "折扣", "2024-11-01", "2024-11-11", 0.75, None, None),
    ("PR010", "双12 满减", "满减", "2024-12-01", "2024-12-12", None, 399.00, 40.00),
    ("PR011", "冬季会员日", "会员日", "2024-12-20", "2024-12-25", 0.85, None, None),
    ("PR012", "满额赠礼", "赠品", "2024-01-01", "2024-12-31", None, None, None),
]

SURNAMES = list("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤")
GIVEN_CHARS = list("伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀霞平刚桂英华萍玲燕红鹏辉建文玉兰凤云彬宇浩凯鑫欣怡婷雪梅琳晨阳佳慧嘉宁思远子涵梓萱雨桐一诺")

GENDERS = ["女", "男", "未知"]
GENDER_WEIGHTS = [62, 35, 3]
AGE_GROUPS = ["18岁以下", "18-24", "25-30", "31-40", "40岁以上"]
AGE_WEIGHTS = [4, 32, 34, 21, 9]
# 服装零售会员四级：按年度累计消费金额升级
MEMBER_LEVELS = ["普通会员", "银卡会员", "金卡会员", "黑卡会员"]
LEVEL_WEIGHTS = [55, 28, 13, 4]
# 会员池规模：50 家门店的连锁品牌，注册会员量远高于下单会员量
MEMBER_COUNT = 60000

RETURN_REASONS = ["尺码不合适", "不喜欢", "质量问题", "发错货"]
RETURN_REASON_WEIGHTS = [45, 25, 20, 10]
RETURN_TYPES = ["退货", "换货"]
RETURN_TYPE_WEIGHTS = [85, 15]

ORDER_HOURS = list(range(10, 22))
ORDER_HOUR_WEIGHTS = [4, 5, 6, 6, 5, 6, 7, 8, 8, 7, 5, 3]
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 月度销售热度：春节、618、双11、双12 是服装零售的明显峰值
MONTH_FACTORS = [1.15, 0.85, 0.95, 0.95, 1.00, 1.15, 0.80, 0.95, 1.00, 1.20, 1.60, 1.30]


def _price(rng: random.Random, low: int, high: int) -> float:
    """生成 199、299 这类常见吊牌价"""
    value = int(rng.uniform(low, high) // 10 * 10) - 1
    return float(max(9, value))


def build_stores(rng: random.Random):
    """按城市分布生成 50 家门店，并给每家门店一个热度系数"""
    city_region = {city: region_id for region_id, _, city, _, _ in REGIONS}
    stores = []
    index = 1
    for city, count in STORE_PLAN.items():
        for area in AREAS[city][:count]:
            store_id = f"S{index:03d}"
            store_type = "直营店" if index % 25 == 1 else "加盟店"
            open_date = date(2020, 1, 1) + timedelta(days=rng.randint(0, 1400))
            area_sqm = round(rng.uniform(80, 260), 1)
            # 热度系数决定每天的单量，让“头部门店”这类问题有真实分布
            popularity = rng.uniform(0.7, 1.6)
            stores.append(
                (
                    store_id,
                    f"{city}{area}店",
                    city_region[city],
                    store_type,
                    open_date,
                    "营业",
                    area_sqm,
                    popularity,
                )
            )
            index += 1

    # 末尾三家门店分别设为闭店和筹备，问数时需要先筛 status
    for position, status in ((-3, "闭店"), (-2, "闭店"), (-1, "筹备")):
        store = list(stores[position])
        store[5] = status
        stores[position] = tuple(store)

    return stores


def build_products(rng: random.Random):
    """按品类生成 300 个款(SPU)，并分配季节、上市日期和吊牌价"""
    products = []
    product_index = 0

    for category, spec in CATEGORY_SPECS.items():
        count = spec["count"]
        old_count = round(count * 0.23)
        spring_count = round(count * 0.38)
        for local_index in range(count):
            product_index += 1
            product_id = f"P{product_index:03d}"

            adjs = spec["adjs"]
            types = spec["types"]
            product_name = f"{adjs[local_index % len(adjs)]}{types[(local_index // len(adjs)) % len(types)]}"

            if local_index < old_count:
                year_season = "2023秋冬"
                season = "秋冬"
                launch_date = date(2023, 8, 1) + timedelta(days=rng.randint(0, 121))
                status = "在售" if rng.random() < 0.55 else "下架"
            elif local_index < old_count + spring_count:
                year_season = "2024春夏"
                season = "春夏"
                launch_date = date(2024, 1, 15) + timedelta(days=rng.randint(0, 136))
                status = "在售" if rng.random() < 0.96 else "下架"
            else:
                year_season = "2024秋冬"
                season = "秋冬"
                launch_date = date(2024, 8, 1) + timedelta(days=rng.randint(0, 91))
                status = "在售"

            list_price = _price(rng, *spec["price_range"])
            cost_price = round(list_price * rng.uniform(*spec["cost_ratio"]), 2)

            products.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "category": category,
                    "series": rng.choice(spec["series"]),
                    "season": season,
                    "year_season": year_season,
                    "list_price": list_price,
                    "cost_price": cost_price,
                    "launch_date": launch_date,
                    "status": status,
                    "weight": rng.choices([1, 2, 3, 4, 5], weights=[20, 30, 25, 15, 10], k=1)[0],
                }
            )

    return products


def build_skus(rng: random.Random, products):
    """每个款展开成 颜色 × 尺码 的 SKU"""
    skus = []
    barcode_seq = 0

    for product in products:
        spec = CATEGORY_SPECS[product["category"]]
        color_count = rng.choices([2, 3, 4], weights=[35, 45, 20], k=1)[0]
        colors = rng.sample(spec["colors"], k=min(color_count, len(spec["colors"])))

        for color_index, color in enumerate(colors, start=1):
            for size in spec["sizes"]:
                barcode_seq += 1
                skus.append(
                    {
                        "sku_id": f"{product['product_id']}-{color_index:02d}-{size}",
                        "product_id": product["product_id"],
                        "color": color,
                        "size": size,
                        "barcode": f"69{barcode_seq:011d}",
                    }
                )

    return skus


def build_store_assortment(rng: random.Random, stores, skus):
    """为每家门店生成上架 SKU 清单，大店铺货更全"""
    store_skus: dict[str, list[dict]] = {}
    for store in stores:
        store_id = store[0]
        area_sqm = store[6]
        probability = 0.30 + min(area_sqm, 260) / 260 * 0.15
        store_skus[store_id] = [sku for sku in skus if rng.random() < probability]
    return store_skus


def build_dates():
    """展开 2024-01-01 到 2024-12-31 的日期维度"""
    dates = []
    current = START_DATE
    while current <= END_DATE:
        dates.append(
            (
                int(current.strftime("%Y%m%d")),
                current,
                current.year,
                f"Q{(current.month - 1) // 3 + 1}",
                current.month,
                current.day,
                current.isoweekday(),
                WEEKDAY_NAMES[current.isoweekday() - 1],
                1 if current.isoweekday() >= 6 else 0,
            )
        )
        current += timedelta(days=1)
    return dates


def build_members(rng: random.Random, stores):
    """生成 MEMBER_COUNT 位会员，注册门店只落在营业中的门店上"""
    open_store_ids = [store[0] for store in stores if store[5] == "营业"]
    members = []
    for index in range(1, MEMBER_COUNT + 1):
        member_name = rng.choice(SURNAMES) + "".join(
            rng.choice(GIVEN_CHARS) for _ in range(rng.choice([1, 2]))
        )
        register_date = date(2022, 1, 1) + timedelta(days=rng.randint(0, 1095))
        members.append(
            (
                f"M{index:05d}",
                member_name,
                rng.choices(GENDERS, weights=GENDER_WEIGHTS, k=1)[0],
                rng.choices(AGE_GROUPS, weights=AGE_WEIGHTS, k=1)[0],
                rng.choices(MEMBER_LEVELS, weights=LEVEL_WEIGHTS, k=1)[0],
                register_date,
                rng.choice(open_store_ids),
            )
        )

    # 按注册日期排序，下单时只从“当天已经注册”的会员里选，避免出现未来会员
    members.sort(key=lambda item: item[5])
    return members


def build_promotions():
    promotions = []
    for (
        promotion_id,
        name,
        promotion_type,
        start_date,
        end_date,
        discount_rate,
        threshold_amount,
        reduce_amount,
    ) in PROMOTIONS:
        promotions.append(
            {
                "promotion_id": promotion_id,
                "promotion_name": name,
                "promotion_type": promotion_type,
                "start_date": date.fromisoformat(start_date),
                "end_date": date.fromisoformat(end_date),
                "discount_rate": discount_rate,
                "threshold_amount": threshold_amount,
                "reduce_amount": reduce_amount,
            }
        )
    return promotions


def calculate_discount(promotion, order_amount):
    """按活动类型计算订单优惠金额；不满足门槛时返回 0"""
    if promotion is None:
        return 0.0

    promotion_type = promotion["promotion_type"]
    if promotion_type in ("折扣", "会员日", "季末清仓"):
        return round(order_amount * (1 - promotion["discount_rate"]), 2)
    if promotion_type == "满减":
        if order_amount >= promotion["threshold_amount"]:
            return promotion["reduce_amount"]
        return 0.0
    # 赠品活动不改变订单金额，这里视为没有优惠
    return 0.0


def _unit_price(rng: random.Random, product, current_date: date) -> float:
    """越接近上市日期折扣越小，老款进入折扣区，模拟服装的季末折价"""
    age_days = (current_date - product["launch_date"]).days
    if age_days <= 90:
        factor = rng.uniform(0.90, 1.00)
    elif age_days <= 180:
        factor = rng.uniform(0.75, 0.95)
    else:
        factor = rng.uniform(0.55, 0.80)
    return round(product["list_price"] * factor, 2)


def iter_facts(rng, stores, products, store_skus, members, dates, promotions):
    """按天流式生成订单、订单明细和退货记录，避免一次性占用大量内存"""
    open_stores = [store for store in stores if store[5] == "营业"]
    product_by_id = {product["product_id"]: product for product in products}
    member_dates = [member[5] for member in members]
    member_pointer = 0

    order_seq = 0
    return_seq = 0

    # 每家门店只保留在售商品的 SKU，减少每天过滤的开销
    store_on_sale: dict[str, list[dict]] = {}
    for store in open_stores:
        store_id = store[0]
        store_on_sale[store_id] = [
            sku
            for sku in store_skus[store_id]
            if product_by_id[sku["product_id"]]["status"] == "在售"
        ]

    for date_id, current_date, _, _, month, _, weekday, _, _ in dates:
        day_order_rows: list[tuple] = []
        day_item_rows: list[tuple] = []
        day_return_rows: list[tuple] = []

        # 推进会员可下单范围
        while member_pointer < len(members) and member_dates[member_pointer] <= current_date:
            member_pointer += 1

        # 当天生效的活动
        day_promotions = [
            promotion
            for promotion in promotions
            if promotion["start_date"] <= current_date <= promotion["end_date"]
        ]

        month_factor = MONTH_FACTORS[month - 1]
        weekend_factor = 1.35 if weekday >= 6 else 1.0

        for store in open_stores:
            store_id = store[0]
            popularity = store[7]

            # 当天可售的 SKU：商品在售且已经上市
            day_skus = [
                sku
                for sku in store_on_sale[store_id]
                if product_by_id[sku["product_id"]]["launch_date"] <= current_date
            ]
            if not day_skus:
                continue
            day_weights = [product_by_id[sku["product_id"]]["weight"] for sku in day_skus]

            order_count = max(
                2, int(rng.uniform(5, 11) * popularity * month_factor * weekend_factor)
            )

            for _ in range(order_count):
                order_seq += 1
                order_id = f"SO{date_id}{order_seq:06d}"

                line_count = rng.choices([1, 2, 3], weights=[45, 35, 20], k=1)[0]
                chosen_skus = rng.choices(day_skus, weights=day_weights, k=line_count)

                lines = []
                order_amount = 0.0
                total_quantity = 0

                for line_no, sku in enumerate(chosen_skus, start=1):
                    product = product_by_id[sku["product_id"]]
                    quantity = rng.choices([1, 2], weights=[90, 10], k=1)[0]
                    unit_price = _unit_price(rng, product, current_date)
                    item_amount = round(unit_price * quantity, 2)

                    lines.append(
                        {
                            "order_item_id": f"SOI{order_seq:07d}{line_no:02d}",
                            "order_id": order_id,
                            "sku_id": sku["sku_id"],
                            "quantity": quantity,
                            "unit_price": unit_price,
                            "item_amount": item_amount,
                            "discount_amount": 0.0,
                        }
                    )
                    order_amount += item_amount
                    total_quantity += quantity

                order_amount = round(order_amount, 2)

                # 30% 的订单参与活动；算不出优惠就不挂活动
                promotion = None
                discount_amount = 0.0
                if day_promotions and rng.random() < 0.30:
                    candidate = rng.choice(day_promotions)
                    candidate_discount = calculate_discount(candidate, order_amount)
                    if candidate_discount > 0:
                        promotion = candidate
                        discount_amount = round(min(candidate_discount, order_amount), 2)

                # 把订单级优惠按明细金额比例分摊，保证明细优惠合计等于订单优惠
                if discount_amount > 0:
                    remaining = discount_amount
                    for index, line in enumerate(lines):
                        if index == len(lines) - 1:
                            allocated = round(remaining, 2)
                        else:
                            allocated = round(
                                discount_amount * line["item_amount"] / order_amount, 2
                            )
                            remaining -= allocated
                        line["discount_amount"] = max(0.0, allocated)

                status_roll = rng.random()
                if status_roll < 0.02:
                    order_status = "已取消"
                elif status_roll < 0.06:
                    order_status = "已退货"
                else:
                    order_status = "已完成"

                # 退货和取消的订单不计入实收；保留原价和优惠，方便演示口径过滤
                if order_status == "已取消":
                    actual_amount = 0.0
                elif order_status == "已退货":
                    actual_amount = 0.0
                else:
                    actual_amount = round(order_amount - discount_amount, 2)

                member_id = None
                if member_pointer > 0 and rng.random() < 0.70:
                    member_id = members[rng.randrange(member_pointer)][0]

                channel = rng.choices(
                    CHANNELS, weights=[channel[4] for channel in CHANNELS], k=1
                )[0]

                hour = rng.choices(ORDER_HOURS, weights=ORDER_HOUR_WEIGHTS, k=1)[0]
                order_time = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    hour,
                    rng.randint(0, 59),
                    rng.randint(0, 59),
                )

                day_order_rows.append(
                    (
                        order_id,
                        store_id,
                        member_id,
                        date_id,
                        channel[0],
                        promotion["promotion_id"] if promotion else None,
                        order_amount,
                        discount_amount,
                        actual_amount,
                        total_quantity,
                        order_status,
                        order_time,
                    )
                )
                day_item_rows.extend(
                    (
                        line["order_item_id"],
                        line["order_id"],
                        line["sku_id"],
                        line["quantity"],
                        line["unit_price"],
                        line["item_amount"],
                        line["discount_amount"],
                    )
                    for line in lines
                )

                # 整单退货：每个明细都生成一条退货记录
                if order_status == "已退货":
                    return_date = min(
                        END_DATE, current_date + timedelta(days=rng.randint(1, 10))
                    )
                    for line in lines:
                        return_seq += 1
                        day_return_rows.append(
                            (
                                f"RT{return_seq:08d}",
                                order_id,
                                line["sku_id"],
                                int(return_date.strftime("%Y%m%d")),
                                line["quantity"],
                                round(line["item_amount"] - line["discount_amount"], 2),
                                "退货",
                                rng.choices(
                                    RETURN_REASONS,
                                    weights=RETURN_REASON_WEIGHTS,
                                    k=1,
                                )[0],
                            )
                        )
                # 部分退货：从已完成订单里随机挑一条明细退回
                elif order_status == "已完成" and rng.random() < 0.06:
                    line = rng.choice(lines)
                    return_date = min(
                        END_DATE, current_date + timedelta(days=rng.randint(1, 10))
                    )
                    return_quantity = line["quantity"]
                    return_seq += 1
                    day_return_rows.append(
                        (
                            f"RT{return_seq:08d}",
                            order_id,
                            line["sku_id"],
                            int(return_date.strftime("%Y%m%d")),
                            return_quantity,
                            round(
                                line["unit_price"] * return_quantity
                                - line["discount_amount"],
                                2,
                            ),
                            rng.choices(
                                RETURN_TYPES, weights=RETURN_TYPE_WEIGHTS, k=1
                            )[0],
                            rng.choices(
                                RETURN_REASONS, weights=RETURN_REASON_WEIGHTS, k=1
                            )[0],
                        )
                    )

        # 每生成完一天就交给调用方写入，避免整年数据堆在内存里
        yield day_order_rows, day_item_rows, day_return_rows


def build_inventory_month(
    rng, snapshot_date_id, open_stores, store_skus, product_by_id
):
    """生成一个月的门店 SKU 库存快照"""
    rows = []
    for store in open_stores:
        store_id = store[0]
        for sku in store_skus[store_id]:
            product = product_by_id[sku["product_id"]]
            hotness = product["weight"]

            if rng.random() < 0.05 + hotness * 0.02:
                available = 0
            elif rng.random() < 0.35:
                available = rng.randint(1, 5)
            elif rng.random() < 0.75:
                available = rng.randint(6, 15)
            else:
                available = rng.randint(16, 40)

            on_hand = available + rng.randint(0, 3)
            rows.append((snapshot_date_id, store_id, sku["sku_id"], on_hand, available))
    return rows


async def insert_in_batches(cursor, sql: str, rows: list[tuple], batch_size=1000):
    for start in range(0, len(rows), batch_size):
        await cursor.executemany(sql, rows[start : start + batch_size])


def month_end_dates():
    """返回 2024 年每个月的月末日期"""
    result = []
    for month in range(1, 13):
        last_day = calendar.monthrange(2024, month)[1]
        result.append(date(2024, month, last_day))
    return result


async def seed():
    rng = random.Random(SEED)

    stores = build_stores(rng)
    products = build_products(rng)
    skus = build_skus(rng, products)
    store_skus = build_store_assortment(rng, stores, skus)
    dates = build_dates()
    members = build_members(rng, stores)
    promotions = build_promotions()

    db = app_config.db_dw
    conn = await asyncmy.connect(
        host=db.host,
        port=db.port,
        user=db.user,
        password=db.password,
        db=db.database,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        async with conn.cursor() as cursor:
            for table in (
                "fact_inventory",
                "fact_return",
                "fact_order_item",
                "fact_order",
                "dim_member",
                "dim_date",
                "dim_promotion",
                "dim_channel",
                "dim_sku",
                "dim_product",
                "dim_store",
                "dim_region",
            ):
                await cursor.execute(f"TRUNCATE TABLE {table}")

            await cursor.executemany(
                "INSERT INTO dim_region (region_id, province, city, city_level, region_name) VALUES (%s, %s, %s, %s, %s)",
                REGIONS,
            )
            await cursor.executemany(
                "INSERT INTO dim_store (store_id, store_name, region_id, store_type, open_date, status, area_sqm) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [
                    (store[0], store[1], store[2], store[3], store[4], store[5], store[6])
                    for store in stores
                ],
            )
            await cursor.executemany(
                "INSERT INTO dim_product (product_id, product_name, category, series, season, year_season, list_price, cost_price, launch_date, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        product["product_id"],
                        product["product_name"],
                        product["category"],
                        product["series"],
                        product["season"],
                        product["year_season"],
                        product["list_price"],
                        product["cost_price"],
                        product["launch_date"],
                        product["status"],
                    )
                    for product in products
                ],
            )
            await cursor.executemany(
                "INSERT INTO dim_sku (sku_id, product_id, color, size, barcode) VALUES (%s, %s, %s, %s, %s)",
                [
                    (
                        sku["sku_id"],
                        sku["product_id"],
                        sku["color"],
                        sku["size"],
                        sku["barcode"],
                    )
                    for sku in skus
                ],
            )
            await cursor.executemany(
                "INSERT INTO dim_channel (channel_id, channel_name, channel_type, platform) VALUES (%s, %s, %s, %s)",
                [(channel[0], channel[1], channel[2], channel[3]) for channel in CHANNELS],
            )
            await cursor.executemany(
                "INSERT INTO dim_promotion (promotion_id, promotion_name, promotion_type, start_date, end_date, discount_rate, threshold_amount, reduce_amount) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        promotion["promotion_id"],
                        promotion["promotion_name"],
                        promotion["promotion_type"],
                        promotion["start_date"],
                        promotion["end_date"],
                        promotion["discount_rate"],
                        promotion["threshold_amount"],
                        promotion["reduce_amount"],
                    )
                    for promotion in promotions
                ],
            )
            await cursor.executemany(
                "INSERT INTO dim_date (date_id, date, year, quarter, month, day, weekday, weekday_name, is_weekend) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                dates,
            )
            await cursor.executemany(
                "INSERT INTO dim_member (member_id, member_name, gender, age_group, member_level, register_date, register_store_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                members,
            )

            order_count = 0
            item_count = 0
            return_count = 0
            for day_orders, day_items, day_returns in iter_facts(
                rng, stores, products, store_skus, members, dates, promotions
            ):
                await insert_in_batches(
                    cursor,
                    "INSERT INTO fact_order (order_id, store_id, member_id, date_id, channel_id, promotion_id, order_amount, discount_amount, actual_amount, item_count, order_status, order_time) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    day_orders,
                )
                await insert_in_batches(
                    cursor,
                    "INSERT INTO fact_order_item (order_item_id, order_id, sku_id, quantity, unit_price, item_amount, discount_amount) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    day_items,
                )
                await insert_in_batches(
                    cursor,
                    "INSERT INTO fact_return (return_id, order_id, sku_id, return_date_id, quantity, return_amount, return_type, return_reason) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    day_returns,
                )
                order_count += len(day_orders)
                item_count += len(day_items)
                return_count += len(day_returns)

            open_stores = [store for store in stores if store[5] == "营业"]
            product_by_id = {product["product_id"]: product for product in products}
            inventory_count = 0
            for snapshot_date in month_end_dates():
                snapshot_date_id = int(snapshot_date.strftime("%Y%m%d"))
                inventory_rows = build_inventory_month(
                    rng, snapshot_date_id, open_stores, store_skus, product_by_id
                )
                await insert_in_batches(
                    cursor,
                    "INSERT INTO fact_inventory (snapshot_date_id, store_id, sku_id, on_hand_qty, available_qty) VALUES (%s, %s, %s, %s, %s)",
                    inventory_rows,
                )
                inventory_count += len(inventory_rows)

        await conn.commit()
        print(
            f"服装数仓造数完成：门店 {len(stores)}，款 {len(products)}，SKU {len(skus)}，"
            f"会员 {len(members)}，日期 {len(dates)}，订单 {order_count}，"
            f"订单明细 {item_count}，退货 {return_count}，库存快照 {inventory_count}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
