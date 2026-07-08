def screenshot_filename(room_id, captured_at, step_code, label):
    return "蓝屏数据截图_%s__%s_%s_%s.png" % (
        room_id,
        captured_at.strftime("%Y%m%d_%H%M%S"),
        step_code,
        label,
    )


def zip_filename(room_id, captured_at):
    return "蓝屏数据截图_%s__%s.zip" % (room_id, captured_at.strftime("%Y%m%d"))
