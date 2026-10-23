SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS dw DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
GRANT ALL PRIVILEGES ON dw.* TO 'goblin'@'%';
USE dw;

-- 服装连锁零售数仓
-- 粒度：订单事实表一行一个订单，订单明细表一行一个 SKU
-- 退货事实表一行一条退货记录，库存事实表一行一个门店 SKU 的月末库存快照
-- 维表与事实表数据由 app/scripts/seed_apparel_dw.py 生成

DROP TABLE IF EXISTS fact_inventory;
DROP TABLE IF EXISTS fact_return;
DROP TABLE IF EXISTS fact_order_item;
DROP TABLE IF EXISTS fact_order;
DROP TABLE IF EXISTS dim_promotion;
DROP TABLE IF EXISTS dim_channel;
DROP TABLE IF EXISTS dim_sku;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_member;
DROP TABLE IF EXISTS dim_store;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_region;


CREATE TABLE dim_region
(
    region_id   VARCHAR(20) PRIMARY KEY COMMENT '区域编号',
    province    VARCHAR(50) COMMENT '省份',
    city        VARCHAR(50) COMMENT '城市',
    city_level  VARCHAR(20) COMMENT '城市等级(一线/新一线/二线/三线)',
    region_name VARCHAR(50) COMMENT '大区'
) COMMENT '地区维度表：城市粒度，用于门店归属和大区分析';


CREATE TABLE dim_store
(
    store_id   VARCHAR(20) PRIMARY KEY COMMENT '门店编号',
    store_name VARCHAR(100) COMMENT '门店名称',
    region_id  VARCHAR(20) COMMENT '所属区域编号',
    store_type VARCHAR(20) COMMENT '门店类型(直营店/加盟店)',
    open_date  DATE COMMENT '开业日期',
    status     VARCHAR(20) COMMENT '门店状态(营业/闭店/筹备)',
    area_sqm   DECIMAL(8, 2) COMMENT '门店营业面积(平方米)'
) COMMENT '门店维度表：一行一家服装连锁门店';


CREATE TABLE dim_product
(
    product_id   VARCHAR(20) PRIMARY KEY COMMENT '款号',
    product_name VARCHAR(100) COMMENT '商品款名',
    category     VARCHAR(30) COMMENT '品类(女装/男装/童装/鞋履/配饰)',
    series       VARCHAR(30) COMMENT '产品线(通勤/休闲/运动/户外/童趣/基础)',
    season       VARCHAR(20) COMMENT '季节(春夏/秋冬/四季)',
    year_season  VARCHAR(20) COMMENT '年份季节(如 2024春夏)',
    list_price   DECIMAL(8, 2) COMMENT '吊牌价(元)',
    cost_price   DECIMAL(8, 2) COMMENT '单位成本(元)',
    launch_date  DATE COMMENT '上市日期',
    status       VARCHAR(20) COMMENT '商品状态(在售/下架)'
) COMMENT '商品维度表：一行一个款(SPU)';


CREATE TABLE dim_sku
(
    sku_id     VARCHAR(30) PRIMARY KEY COMMENT 'SKU 编号',
    product_id VARCHAR(20) COMMENT '所属款号',
    color      VARCHAR(20) COMMENT '颜色',
    size       VARCHAR(10) COMMENT '尺码',
    barcode    VARCHAR(30) COMMENT '条码',
    KEY idx_sku_product (product_id)
) COMMENT 'SKU 维度表：一行一个颜色尺码组合';


CREATE TABLE dim_member
(
    member_id         VARCHAR(20) PRIMARY KEY COMMENT '会员编号',
    member_name       VARCHAR(50) COMMENT '会员姓名',
    gender            VARCHAR(10) COMMENT '性别',
    age_group         VARCHAR(20) COMMENT '年龄段',
    member_level      VARCHAR(20) COMMENT '会员等级',
    register_date     DATE COMMENT '注册日期',
    register_store_id VARCHAR(20) COMMENT '注册门店编号'
) COMMENT '会员维度表：一行一位注册会员';


CREATE TABLE dim_channel
(
    channel_id   VARCHAR(20) PRIMARY KEY COMMENT '渠道编号',
    channel_name VARCHAR(50) COMMENT '渠道名称',
    channel_type VARCHAR(20) COMMENT '渠道类型(线下/线上/私域)',
    platform     VARCHAR(50) COMMENT '所属平台'
) COMMENT '渠道维度表：线下门店、线上商城与私域渠道';


CREATE TABLE dim_promotion
(
    promotion_id     VARCHAR(20) PRIMARY KEY COMMENT '活动编号',
    promotion_name   VARCHAR(100) COMMENT '活动名称',
    promotion_type   VARCHAR(30) COMMENT '活动类型(折扣/满减/会员日/季末清仓/赠品)',
    start_date       DATE COMMENT '开始日期',
    end_date         DATE COMMENT '结束日期',
    discount_rate    DECIMAL(4, 2) COMMENT '折扣率(0.8 表示八折)',
    threshold_amount DECIMAL(8, 2) COMMENT '满减门槛金额(元)',
    reduce_amount    DECIMAL(8, 2) COMMENT '满减减免金额(元)'
) COMMENT '促销活动维度表：折扣、满减、会员日、季末清仓等';


CREATE TABLE dim_date
(
    date_id      INT PRIMARY KEY COMMENT '日期编号 yyyyMMdd',
    date         DATE COMMENT '业务日期',
    year         INT COMMENT '年份',
    quarter      VARCHAR(2) COMMENT '季度',
    month        INT COMMENT '月份',
    day          INT COMMENT '日',
    weekday      INT COMMENT '星期几(1=周一)',
    weekday_name VARCHAR(10) COMMENT '星期名称',
    is_weekend   TINYINT COMMENT '是否周末(1是/0否)'
) COMMENT '日期维度表：2024 年按天展开';


CREATE TABLE fact_order
(
    order_id        VARCHAR(40) PRIMARY KEY COMMENT '订单编号',
    store_id        VARCHAR(20) COMMENT '门店编号',
    member_id       VARCHAR(20) COMMENT '会员编号(非会员下单为空)',
    date_id         INT COMMENT '下单日期编号',
    channel_id      VARCHAR(20) COMMENT '下单渠道编号',
    promotion_id    VARCHAR(20) COMMENT '使用的促销活动编号',
    order_amount    DECIMAL(10, 2) COMMENT '原价金额(元)',
    discount_amount DECIMAL(10, 2) COMMENT '优惠金额(元)',
    actual_amount   DECIMAL(10, 2) COMMENT '实收金额(元)',
    item_count      INT COMMENT '购买件数',
    order_status    VARCHAR(20) COMMENT '订单状态(已完成/已退货/已取消)',
    order_time      DATETIME COMMENT '下单时间',
    KEY idx_order_store (store_id),
    KEY idx_order_member (member_id),
    KEY idx_order_date (date_id),
    KEY idx_order_channel (channel_id)
) COMMENT '订单事实表：一行一个订单';


CREATE TABLE fact_order_item
(
    order_item_id   VARCHAR(40) PRIMARY KEY COMMENT '订单明细编号',
    order_id        VARCHAR(40) COMMENT '订单编号',
    sku_id          VARCHAR(30) COMMENT 'SKU 编号',
    quantity        INT COMMENT '购买件数',
    unit_price      DECIMAL(8, 2) COMMENT '成交单价(元)',
    item_amount     DECIMAL(10, 2) COMMENT '明细金额(元)',
    discount_amount DECIMAL(8, 2) COMMENT '明细优惠金额(元)',
    KEY idx_item_order (order_id),
    KEY idx_item_sku (sku_id)
) COMMENT '订单明细事实表：一行一个 SKU';


CREATE TABLE fact_return
(
    return_id       VARCHAR(40) PRIMARY KEY COMMENT '退货单编号',
    order_id        VARCHAR(40) COMMENT '原订单编号',
    sku_id          VARCHAR(30) COMMENT '退货 SKU 编号',
    return_date_id  INT COMMENT '退货日期编号',
    quantity        INT COMMENT '退货件数',
    return_amount   DECIMAL(10, 2) COMMENT '退货金额(元)',
    return_type     VARCHAR(20) COMMENT '退货类型(退货/换货)',
    return_reason   VARCHAR(30) COMMENT '退货原因(尺码不合适/质量问题/不喜欢/发错货)',
    KEY idx_return_order (order_id),
    KEY idx_return_sku (sku_id),
    KEY idx_return_date (return_date_id)
) COMMENT '退货事实表：一行一条退货记录';


CREATE TABLE fact_inventory
(
    snapshot_date_id INT COMMENT '快照日期编号(月末)',
    store_id         VARCHAR(20) COMMENT '门店编号',
    sku_id           VARCHAR(30) COMMENT 'SKU 编号',
    on_hand_qty      INT COMMENT '在库数量',
    available_qty    INT COMMENT '可售数量',
    PRIMARY KEY (snapshot_date_id, store_id, sku_id),
    KEY idx_inventory_store (store_id),
    KEY idx_inventory_sku (sku_id)
) COMMENT '库存事实表：门店 SKU 月末库存快照';
