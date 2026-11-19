# Folia Player — 部署 & APK 打包指南（免裝任何工具版）

## 🎯 整体流程

```
1. 推代码到 GitHub
      ↓
2. Railway 自动部署（免费，2 分钟）
      ↓
3. 拿到 https://xxx.up.railway.app
      ↓
4. 打开 PWABuilder → 输入 URL → 一键下载 APK ✅
```

---

## 🌟 为什么选 PWABuilder？

| 传统方式 | PWABuilder |
|----------|------------|
| 装 Java JDK（100MB） | ❌ 不用 |
| 装 Android SDK（1GB+） | ❌ 不用 |
| 装 Gradle | ❌ 不用 |
| 编译十几分钟 | ✅ 30 秒 |
| 环境容易坏 | ✅ 微软官方云服务 |

**PWABuilder 是微软官方免费服务，把你网站打包成 Android/iOS/Windows App。**

---

## 📦 第一步：推到 GitHub

```bash
cd FoliaPlayer
git init
git add .
git commit -m "Folia Player v1"
git remote add origin https://github.com/你的用户名/folia-player.git
git push -u origin main
```

---

## 🚀 第二步：Railway 部署（完全免费）

### 1. 注册
打开 **https://railway.app** ，用 GitHub 账号登录（首次送 $5 额度）

### 2. 部署
- **New Project** → **Deploy from GitHub repo**
- 选你的 `folia-player` 仓库
- Branch 选 `main`
- 点 **Deploy Now**

### 3. 等待约 2 分钟
Railway 自动：
- 装依赖（npm install）
- 启动服务（node server.js）
- 分配 HTTPS 域名 → `https://folia-player-xxx.up.railway.app`

### 4. ✅ 验证
浏览器打开 `https://你的域名/api/ping`，应该返回：
```json
{"status":"ok","message":"网易云音乐服务运行中","apis":440}
```

---

## 📱 第三步：PWABuilder 一键打包 APK

### 1. 打开 PWABuilder
👉 **https://www.pwabuilder.com**

### 2. 输入你的网址
```
https://folia-player-xxx.up.railway.app
```
点 **Start**

### 3. 查看扫描结果
PWABuilder 会检查你的网站：
- ✅ Manifest（我们已配好 manifest.json）
- ✅ Service Worker（我们已配好 sw.js）
- ✅ HTTPS（Railway 自动提供）
- ✅ Icons（我们已生成 192 + 512 PNG）

**理想情况：全绿 ✅**

### 4. 打包 Android APK
- 点中间大按钮 **Package for Stores**
- 选 **Android** → **Android App Package**
- 填信息：
  - Package ID: `com.folia.player`
  - App name: `Folia Player`
  - 版本号: `1.0.0`
- 点 **Generate Package**
- **等待约 30 秒**

### 5. 下载 APK
点 **Download** → 得到 `com.folia.player.apk`（约 2MB）

### 6. 安装到手机
- **方式 A**：微信传文件到手机 → 点击安装
- **方式 B**：QQ/云盘下载安装
- 手机需在设置里允许"未知来源安装"

✅ **完成！你有了一个自己的 Android App！**

---

## 🎨 可选：自定义图标/名称

### 改 App 图标
替换 `public/` 下的两个文件：
- `icon-192.png`（192×192）
- `icon-512.png`（512×512）

随便用什么工具做 — Figma / Canva / Photoshop / 在线工具 https://www.favicon-generator.org/

### 改 App 名称
编辑 `public/manifest.json`：
```json
{
  "name": "你的应用名",
  "short_name": "簡稱"
}
```

改完后：
```bash
git add . && git commit -m "改图标" && git push
# Railway 自动重新部署
# 再去 PWABuilder 重新打包一次
```

---

## 🔁 更新 App

```bash
# 改了代码后
git add . && git commit -m "update" && git push
# Railway 自动重新部署（约 1 分钟）
# 再去 PWABuilder 重新打包一次 APK
# 手机装新版（覆盖安装即可）
```

---

## ⚠️ 注意事项

| 问题 | 解决 |
|------|------|
| Railway 免费版会休眠 | 15 分钟没访问自动休眠，打开要等 5-15 秒冷启动 |
| Cookie 会丢 | Railway 免费版容器重启会重置，需要重新扫码登录 |
| 网易云 CDN 在海外慢 | 网易云封面图是国内 CDN，Railway 在海外可能加载慢。可以考虑用国内服务器（阿里云/腾讯云轻量） |
| PWABuilder 扫描有红叉 | 大部分可以忽略，只要不是 PWA Required 级别 |
| 想上架 Google Play | 需要注册 Google Play Developer 账号（$25 一次性）+ 用 Bubblewrap 正式签名 |
| 想要 iOS App | PWABuilder 也能生成 iOS，但需要 Mac + Apple 开发者账号（$99/年） |

---

## 🆘 常见问题

**Q: PWABuilder 报 "Manifest not found"**
A: 确认 https://你的域名/manifest.json 能直接访问

**Q: PWABuilder 报 "Icons missing"**
A: 确认 https://你的域名/icon-192.png 和 icon-512.png 能访问

**Q: 装到手机后打不开白屏**
A: 可能 Railway 休眠了，先用手机浏览器打开 https://你的域名 唤醒，再开 App

**Q: 封面图/音乐加载慢**
A: 网易云官方 CDN（music.126.net / music.163.com）在国内访问快，但海外服务器代理它慢。解决：
   1. 换 Railway Hong Kong 区域部署
   2. 或者换国内云服务器（腾讯云轻量，约 35 元/月）

**Q: 想要完全离线可用的 App**
A: 用 Capacitor 把 Node.js runtime 嵌进去，APK 会很大（200MB+），另外再做。当前 TWA 方案本质是内嵌浏览器打开你的网站。

---

## 📊 项目结构

```
FoliaPlayer/
├── server.js              后端（PORT 支持 process.env）
├── package.json           npm start
├── public/
│   ├── index.html         手机端 UI
│   ├── style.css          Folia 主题
│   ├── app.js             前端逻辑
│   ├── manifest.json      ✅ PWA manifest
│   ├── sw.js              ✅ Service Worker
│   ├── icon-192.png       ✅ 192×192 应用图标
│   └── icon-512.png       ✅ 512×512 应用图标
├── railway.toml           Railway 配置
├── render.yaml            Render 配置（备选）
└── DEPLOY.md              本文件
```
