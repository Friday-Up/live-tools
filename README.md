# 直播运营工具

直播相关本地工具统一仓库。Windows 业务用户只需要下载打包文件并双击启动脚本，不需要关心内部模块目录。

## Windows 使用

1. 下载 GitHub Actions 或 Release 生成的 `Live-Tools-Windows.zip`。
2. 解压 zip。
3. 双击 `启动直播工具.bat`。
4. 浏览器自动打开 `http://127.0.0.1:8080`。
5. 在页面里选择功能：
   - `SKU 测价`
   - `绑定券码/促销ID`
6. 用完后双击自动生成的 `关闭服务.bat`。

## 源码运行

macOS / Linux：

```bash
cd live-web
./start.sh
```

Windows 源码模式：

```bat
启动直播工具.bat
```

## 目录

- `live-web/`：统一页面、启动服务和 API，是唯一打包入口。
- `live-promotion-binding/`：绑定券码/促销ID 核心逻辑，生成京东官方上传模板和异常报告。
- `live-sku-price-audit/`：SKU 测价核心逻辑，供统一页面调用。
- `.github/workflows/build-windows.yml`：Windows 打包流程。
- `docs/`：方案、SOP 和实施计划。

## 发版说明

仓库按 `live-tools` 维护。旧的 `live-sku-price-audit` 只保留为内部模块名，不再作为业务发版项目名。
