from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

from .file_naming import zip_filename


MANIFEST_NAME = "截图清单.xlsx"
HEADERS = ["计划整点", "实际执行时间", "直播间ID", "序号", "截图项", "文件名", "状态", "失败原因"]


def write_manifest_workbook(output_dir, records):
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MANIFEST_NAME
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "截图清单"
    sheet.append(HEADERS)
    for record in records:
        sheet.append(
            [
                record.planned_slot,
                record.executed_at.strftime("%Y-%m-%d %H:%M:%S") if record.executed_at else "",
                record.room_id,
                record.step_code,
                record.step_name,
                record.filename,
                record.status,
                record.error,
            ]
        )
    workbook.save(path)
    return path


def write_zip_archive(output_dir, room_id, captured_at):
    archive_path = output_dir / zip_filename(room_id, captured_at)
    manifest_path = output_dir / MANIFEST_NAME
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as zf:
        if manifest_path.exists():
            zf.write(manifest_path, MANIFEST_NAME)
        for path in sorted(output_dir.rglob("*.png")):
            zf.write(path, path.relative_to(output_dir).as_posix())
    return archive_path
