FLOW_METRICS = {
    "05": "在线人数",
    "06": "访问人数",
    "07": "人均停留时长",
    "08": "成交人数",
    "09": "成交金额",
    "10": "成交单量",
    "11": "直播曝光点击率",
}


def run_capture_step(browser, step):
    if step.code == "01":
        browser.open_overview()
    elif step.code == "02":
        browser.open_overview()
        browser.select_overview_live_tab("在线")
    elif step.code == "03":
        browser.open_overview()
        browser.select_overview_live_tab("成交")
    elif step.code == "04":
        browser.open_overview()
        browser.select_overview_product_scope("挂袋商品")
    elif step.code in FLOW_METRICS:
        browser.open_flow()
        browser.select_flow_metric(FLOW_METRICS[step.code])
    elif step.code == "12":
        browser.open_overview()
        browser.select_user_portrait("访问用户")
    elif step.code == "13":
        browser.open_overview()
        browser.select_user_portrait("成交用户")
    elif step.code == "14":
        browser.open_product()
        browser.sort_product_table("成交件数")
    elif step.code == "15":
        browser.open_product()
        browser.sort_product_table("成交金额")
    else:
        raise ValueError("未知截图项: %s" % step.code)
