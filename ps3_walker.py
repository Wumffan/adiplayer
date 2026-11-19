"""
PS3 像素风 3D 行走 Demo（Pygame + NumPy）

思路：
  - 以低内部分辨率 400x225 渲染，再最近邻放大 3 倍，得到粗颗粒的像素观感；
  - 地面用向量化的 Mode-7 透视采样（伪 3D），世界坐标取模 -> 无限延伸的草地；
  - 天空与云为一次性预渲染表面，云层随视角水平视差滚动 -> 无限天空盒；
  - 全程无外部素材，草地纹理程序化生成，单文件即可运行。

操作：
  W / S      前进 / 后退
  A / D      左移 / 右移
  ← / →      左右转头
  ↑ / ↓      抬头 / 低头
  Shift      疾跑
  Esc        退出
"""

import math
import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np
import pygame

# ------------------------------------------------------------------
# 渲染配置
# ------------------------------------------------------------------
W, H = 400, 225          # 内部渲染分辨率（小 -> 压力低，且天然像素感）
SCALE = 3                # 放大倍率（最近邻）
WIN_W, WIN_H = W * SCALE, H * SCALE

FOCAL = 150.0            # 焦距（像素）
HORIZON = 103            # 地平线所在行
CAM_H = 1.65             # 相机离地高度（世界单位）
NEAR_PLANE = 0.12        # 近裁剪面：跨越它的网格会被裁剪，而不是整片消失

TILE_PX = 64             # 草地纹理边长
TILE_WORLD = 2.2         # 一张纹理覆盖的世界尺寸
FOG_DIST = 62.0          # 雾/空气透视的过渡行数

MOVE_SPEED = 3.2
RUN_SPEED = 6.0
TURN_SPEED = 1.9

SKY_TOP = np.array([46, 118, 212], dtype=np.float32)
SKY_HORIZON = np.array([200, 232, 248], dtype=np.float32)
FOG_COLOR = SKY_HORIZON.copy()

SUN_AZIMUTH = 2.75       # 太阳在世界中的方位角（弧度）：π 即正后方，开局在玩家身后
SUN_ELEV_PX = 52.0       # 太阳高出地平线的像素数
RAINBOW_AZIMUTH = 0.55   # 参考站示例中的低透明度彩虹，固定在世界天空中
SKY_SCALE = W / (2.0 * math.atan((W * 0.5) / FOCAL))  # 天空投影：每弧度对应像素
SKY_PAD = 200            # 天空表面上下预留，供大幅抬头仰望高层塔顶

PITCH_MAX = 190.0        # 俯仰上限（像素）：抬头时可看到真实尺度高楼顶部
PITCH_SPEED = 120.0      # 俯仰速度（像素/秒）

# 场景角色（大白猫）在世界中的位置
TORO_X, TORO_Z = -1.8, 5.0

# 角色光照方向：与场景太阳一致（单位向量）
_sun_el = math.atan2(SUN_ELEV_PX, FOCAL)
LIGHT = (
    math.sin(SUN_AZIMUTH) * math.cos(_sun_el),
    math.sin(_sun_el),
    math.cos(SUN_AZIMUTH) * math.cos(_sun_el),
)

# 按距离分层的纹理采样：远处用降采样 mip，消除高频闪烁
# (起始行距, 结束行距, mip 级别)
MIP_BANDS = ((1, 34, 2), (34, 72, 1), (72, 10**9, 0))

# Frutiger Aero 城市：玻璃高楼、浅水池和带高光的透明泡泡
PLAYER_RADIUS = 0.45
CITY_HEIGHT_SCALE = 6.0   # 约 33–60 米：以 1.65 米视点为参照的真实高层建筑尺度
CITY_FOOTPRINT_SCALE = 2.0
CITY_POSITION_SCALE = 1.60  # 同步拉开楼间距，避免放大后楼体互相穿插
CITY = [
    (-6.0, 18.0, 3.0, 3.0, 7.0),
    (-1.0, 20.0, 2.5, 2.5, 10.0),
    (4.0, 19.0, 3.5, 3.5, 5.5),
    (8.0, 17.0, 3.0, 3.0, 8.0),
    (-14.0, 8.0, 3.5, 3.5, 9.0),
    (14.0, 6.0, 3.0, 3.0, 7.0),
]
PONDS = [(4.8, 8.5, 4.6, 3.2)]
BUBBLES = [
    (4.0, 3.2, 11.0, 0.55),
    (-5.0, 4.8, 12.0, 0.70),
    (10.0, 5.0, 18.0, 0.80),
    (-11.0, 3.5, 5.0, 0.55),
    (2.0, 5.0, -8.0, 0.60),
    # 草地上的细小露珠，与大尺寸空气泡泡形成尺度层次
    (1.5, 0.20, 4.5, 0.09),
    (-3.0, 0.24, 7.0, 0.12),
    (6.0, 0.26, 5.0, 0.10),
    (3.2, 0.18, 2.8, 0.07),
    (-5.5, 0.22, 2.0, 0.08),
]
LOBBY_BUBBLES = [
    (-1.8, 4.4, 1.0, 0.26),
    (1.7, 4.9, 2.7, 0.34),
    (0.2, 5.5, 4.5, 0.22),
    (-4.0, 2.7, 4.2, 0.18),
    (4.2, 3.4, 0.7, 0.20),
]


# ------------------------------------------------------------------
# 程序化纹理 / 预渲染
# ------------------------------------------------------------------
def make_grass_texture(seed=7):
    """生成可无缝平铺的 64x64 草地纹理（纯程序化，无素材）。"""
    rng = np.random.default_rng(seed)
    tex = np.empty((TILE_PX, TILE_PX, 3), dtype=np.float32)
    tex[:] = (78, 138, 62)

    # 逐像素噪声 -> 天然无缝
    tex += rng.normal(0, 11, (TILE_PX, TILE_PX, 1))
    # 少量细碎亮斑，像草叶受光
    speck = rng.random((TILE_PX, TILE_PX))
    tex[..., 1] += np.where(speck > 0.93, 26, 0)
    tex[..., 0] += np.where(speck > 0.97, 18, 0)

    # 深浅土块：用取模索引绘制，跨越边界也不会产生接缝
    for _ in range(20):
        x, y = rng.integers(0, TILE_PX), rng.integers(0, TILE_PX)
        w, h = rng.integers(6, 23), rng.integers(3, 9)
        rows = (y + np.arange(h)) % TILE_PX
        cols = (x + np.arange(w)) % TILE_PX
        tex[np.ix_(rows, cols)] += rng.uniform(-24, 14)

    return np.clip(tex, 0, 255).astype(np.uint8)


def make_lobby_texture():
    """浅白水磨石与青灰瓷砖缝，带柔和的蓝绿反光。"""
    rng = np.random.default_rng(19)
    tex = np.empty((TILE_PX, TILE_PX, 3), dtype=np.float32)
    tex[:] = (190, 220, 213)
    tex += rng.normal(0, 3.2, (TILE_PX, TILE_PX, 1))
    yy, xx = np.mgrid[0:TILE_PX, 0:TILE_PX]
    sheen = (np.sin((xx+yy) * math.tau / TILE_PX) + 1.0) * 5.0
    tex[..., 1] += sheen
    tex[..., 2] += sheen * 1.5
    tex[0:2, :] = (116, 167, 170)
    tex[:, 0:2] = (116, 167, 170)
    tex[32:33, :] = (157, 199, 195)
    tex[:, 32:33] = (157, 199, 195)
    return np.clip(tex, 0, 255).astype(np.uint8)


def build_mips(tex):
    """构建 2 倍逐级降采样链，供远处地面采样，减轻高频锯齿闪烁。"""
    levels = [tex]
    cur = tex
    while cur.shape[0] >= 16:
        h, w = cur.shape[0] // 2, cur.shape[1] // 2
        cur = cur.reshape(h, 2, w, 2, 3).mean(axis=(1, 3)).astype(np.uint8)
        levels.append(cur)
    return levels


def make_sky():
    """预渲染渐变天空（比屏幕更高，供俯仰时上下平移；地平线处颜色与雾色一致）。"""
    sky_h = H + SKY_PAD * 2
    t = np.clip(
        (np.arange(sky_h, dtype=np.float32) - SKY_PAD) / HORIZON, 0.0, 1.0
    ) ** 0.85
    cols = SKY_TOP[None, :] * (1.0 - t[:, None]) + SKY_HORIZON[None, :] * t[:, None]
    img = np.broadcast_to(cols[:, None, :], (sky_h, W, 3)).astype(np.uint8)
    return pygame.surfarray.make_surface(np.ascontiguousarray(img.transpose(1, 0, 2)))


def make_sun(size=170):
    """预渲染带透明度的太阳光晕，运行时按视角投影到天空。"""
    r = size / 2.0
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.hypot(xx - r, yy - r)
    glow = np.exp(-(d / 52.0) ** 2 * 2.2) * 150.0
    disc = np.clip(1.0 - d / 17.0, 0.0, 1.0) ** 0.5 * 250.0

    rgba = np.empty((size, size, 4), dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 1] = 247
    rgba[..., 2] = 216
    rgba[..., 3] = np.clip(glow + disc, 0, 255).astype(np.uint8)
    return pygame.image.frombuffer(
        rgba.tobytes(), (size, size), "RGBA"
    ).convert_alpha()


def make_aurora():
    """预渲染青绿色极光带，透明度较低，不改变场景光照参数。"""
    cw, ch = W * 2, 92
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    rgba = np.zeros((ch, cw, 4), dtype=np.uint8)
    bands = (
        (27.0, 9.0, 0.0, 9.0, (94, 255, 206)),
        (43.0, 12.0, 1.8, 11.0, (89, 225, 255)),
        (57.0, 7.0, 3.5, 8.0, (185, 255, 224)),
    )
    for base, amp, phase, width, color in bands:
        center = base + amp * np.sin(xx / cw * math.tau * 2.0 + phase)
        alpha = np.exp(-((yy - center) / width) ** 2 * 1.8) * 42.0
        mask = alpha > rgba[..., 3]
        rgba[..., :3][mask] = color
        rgba[..., 3] = np.maximum(rgba[..., 3], alpha.astype(np.uint8))
    return pygame.image.frombuffer(rgba.tobytes(), (cw, ch), "RGBA").convert_alpha()


def make_rainbow():
    """预渲染柔和的七色彩虹弧，参考首页彩虹与泡泡示例。"""
    rw, rh = 260, 140
    yy, xx = np.mgrid[0:rh, 0:rw].astype(np.float32)
    distance = np.hypot(xx - rw * 0.5, (yy - 132.0) * 1.04)
    rgba = np.zeros((rh, rw, 4), dtype=np.uint8)
    colors = (
        (255, 105, 120), (255, 183, 85), (255, 238, 115),
        (112, 230, 153), (92, 202, 248), (137, 160, 250), (194, 140, 238),
    )
    for i, color in enumerate(colors):
        radius = 116.0 - i * 5.0
        alpha = np.exp(-((distance - radius) / 2.6) ** 2) * 68.0
        alpha *= yy < 130.0
        mask = alpha > rgba[..., 3]
        rgba[..., :3][mask] = color
        rgba[..., 3] = np.maximum(rgba[..., 3], alpha.astype(np.uint8))
    return pygame.image.frombuffer(rgba.tobytes(), (rw, rh), "RGBA").convert_alpha()


def _se(v, e):
    """超椭球用的幂函数：e=1 是球，e<1 越接近方盒。"""
    return v ** e if v >= 0.0 else -((-v) ** e)


def _add_sphere(verts, tris, center, radii, seg, ring, color, exponent=1.0, taper=0.0):
    """往网格里加一个低多边形椭球 / 超椭球。

    exponent < 1 会变成圆角方块（多罗猫的矩形身体）；
    taper > 0 会让上窄下宽，形成梯形的头。
    """
    cx, cy, cz = center
    rx, ry, rz = radii
    top = len(verts)
    verts.append((cx, cy + ry, cz))
    rows = []
    for i in range(1, ring):
        phi = math.pi * i / ring
        cv = math.cos(phi)
        sv = _se(math.sin(phi), exponent)
        row = []
        for j in range(seg):
            th = 2.0 * math.pi * j / seg
            width = 1.0 - taper * cv     # 上窄下宽的梯形
            row.append(len(verts))
            verts.append((
                cx + rx * width * sv * _se(math.cos(th), exponent),
                cy + ry * _se(cv, exponent),
                cz + rz * width * sv * _se(math.sin(th), exponent),
            ))
        rows.append(row)
    bot = len(verts)
    verts.append((cx, cy - ry, cz))

    # 统一为外向绕序，法线由顶点顺序算出，光照才不会反
    for j in range(seg):
        tris.append((top, rows[0][(j + 1) % seg], rows[0][j], color))
    for i in range(len(rows) - 1):
        for j in range(seg):
            j2 = (j + 1) % seg
            tris.append((rows[i][j], rows[i + 1][j2], rows[i + 1][j], color))
            tris.append((rows[i][j], rows[i][j2], rows[i + 1][j2], color))
    for j in range(seg):
        tris.append((bot, rows[-1][j], rows[-1][(j + 1) % seg], color))


def _add_capsule(verts, tris, p0, p1, radius, seg, color):
    """两点之间的圆头胶囊，p0 / p1 是最外端的球心投影点。"""
    ax, ay, az = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    length = math.sqrt(ax * ax + ay * ay + az * az) or 1e-9
    ax, ay, az = ax / length, ay / length, az / length

    rx, ry, rz = (0.0, 0.0, 1.0) if abs(ay) < 0.9 else (1.0, 0.0, 0.0)
    ux, uy, uz = ay * rz - az * ry, az * rx - ax * rz, ax * ry - ay * rx
    ul = math.sqrt(ux * ux + uy * uy + uz * uz) or 1e-9
    ux, uy, uz = ux / ul, uy / ul, uz / ul
    vx, vy, vz = ay * uz - az * uy, az * ux - ax * uz, ax * uy - ay * ux

    # 两端各多一圈较小的环，形成圆头而不是尖锥
    specs = (
        (radius * 0.32, radius * 0.72),
        (radius, radius),
        (length - radius, radius),
        (length - radius * 0.32, radius * 0.72),
    )
    rings = []
    for distance, ring_radius in specs:
        cx = p0[0] + ax * distance
        cy = p0[1] + ay * distance
        cz = p0[2] + az * distance
        row = []
        for j in range(seg):
            th = 2.0 * math.pi * j / seg
            cu, su = math.cos(th) * ring_radius, math.sin(th) * ring_radius
            row.append(len(verts))
            verts.append((cx + ux * cu + vx * su, cy + uy * cu + vy * su, cz + uz * cu + vz * su))
        rings.append(row)

    for k in range(len(rings) - 1):
        for j in range(seg):
            j2 = (j + 1) % seg
            tris.append((rings[k][j], rings[k + 1][j2], rings[k + 1][j], color))
            tris.append((rings[k][j], rings[k][j2], rings[k + 1][j2], color))

    for tip, ring, sign in ((p0, rings[0], -1.0), (p1, rings[-1], 1.0)):
        ti = len(verts)
        verts.append(tip)
        for j in range(seg):
            j2 = (j + 1) % seg
            if sign > 0:
                tris.append((ring[j], ring[j2], ti, color))
            else:
                tris.append((ring[j2], ring[j], ti, color))


def _ear_tri(side):
    """位于头顶两侧的耳廓，底部仍与头部网格相交。"""
    return ((side * 0.43, 1.88), (side * 0.18, 1.94), (side * 0.41, 2.42))


def _add_ear(verts, tris, side):
    """白色耳廓，淡黄色内耳在绘制阶段贴到正面。"""
    white = (250, 250, 246)
    depth = 0.05
    i0 = len(verts)
    for x, y in _ear_tri(side):
        verts.append((x, y, depth))
    for x, y in _ear_tri(side):
        verts.append((x, y, -depth))

    def tri_face(a, b, c):
        # 镜像到另一侧时同步反转绕序，保证法线始终朝外
        tris.append((a, c, b, white) if side < 0 else (a, b, c, white))

    tri_face(i0, i0 + 2, i0 + 1)
    tri_face(i0 + 3, i0 + 4, i0 + 5)
    for k in range(3):
        k2 = (k + 1) % 3
        tri_face(i0 + k, i0 + k2, i0 + 3 + k2)
        tri_face(i0 + k, i0 + 3 + k2, i0 + 3 + k)


def build_toro_mesh():
    """按官方立绘重建：圆润梯形头、白耳黄内耳、长方形躯干和圆头四肢。"""
    white = (250, 250, 246)
    verts, tris = [], []
    # 头高与躯干接近，腿约占躯干的七成；头宽约为躯干两倍
    _add_sphere(verts, tris, (0.0, 1.62, 0.0), (0.54, 0.40, 0.38), 24, 16, white,
                exponent=0.62, taper=0.14)
    _add_sphere(verts, tris, (0.0, 0.90, 0.0), (0.27, 0.40, 0.19), 20, 12, white,
                exponent=0.56, taper=0.06)
    for s in (-1, 1):
        _add_capsule(verts, tris, (s * 0.25, 1.18, 0.01), (s * 0.38, 0.55, 0.06), 0.055, 10, white)
        _add_capsule(verts, tris, (s * 0.12, 0.58, 0.0), (s * 0.16, 0.02, 0.04), 0.062, 10, white)
    # 短短的日式猫尾，从躯干后方露出一点
    _add_capsule(verts, tris, (0.20, 0.82, -0.16), (0.40, 0.96, -0.20), 0.050, 8, white)
    _add_ear(verts, tris, -1)
    _add_ear(verts, tris, 1)
    return verts, tris


def make_clouds(seed=3):
    """预渲染一条可横向循环的像素云带（带 alpha）。"""
    rng = np.random.default_rng(seed)
    cw, ch = W * 2, 74
    surf = pygame.Surface((cw, ch), pygame.SRCALPHA)
    for _ in range(16):
        x = int(rng.integers(0, cw))
        y = int(rng.integers(6, 44))
        w = int(rng.integers(34, 96))
        h = int(rng.integers(9, 19))
        for dx in (0, -cw, cw):  # 左右各画一份，保证循环处无缺口
            pygame.draw.ellipse(surf, (255, 255, 255, 44), (x + dx, y, w, h))
            pygame.draw.ellipse(
                surf, (255, 255, 255, 66),
                (x + dx + w * 0.22, y - h * 0.35, w * 0.6, h * 1.15),
            )
    return surf


def _clip_near(points):
    """在相机空间裁剪多边形，保留位于近裁剪面前方的部分。"""
    clipped = []
    previous = points[-1]
    previous_inside = previous[2] >= NEAR_PLANE
    for current in points:
        current_inside = current[2] >= NEAR_PLANE
        if current_inside != previous_inside:
            t = (NEAR_PLANE - previous[2]) / (current[2] - previous[2])
            clipped.append(tuple(
                previous[i] + (current[i] - previous[i]) * t for i in range(3)
            ))
        if current_inside:
            clipped.append(current)
        previous = current
        previous_inside = current_inside
    return clipped


def _emit_quad(verts, tris, points, color, outward):
    """加入一个四边形，并根据外法线自动校正三角形绕序。"""
    a, b, c, d = points
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    if nx * outward[0] + ny * outward[1] + nz * outward[2] < 0.0:
        b, d = d, b
    i = len(verts)
    verts.extend((a, b, c, d))
    tris.append((i, i + 1, i + 2, color))
    tris.append((i, i + 2, i + 3, color))


def _emit_tri(verts, tris, points, color, outward):
    """加入三角形并校正外向绕序，用于圆顶和多边形屋顶。"""
    a, b, c = points
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    if nx * outward[0] + ny * outward[1] + nz * outward[2] < 0.0:
        b, c = c, b
    i = len(verts)
    verts.extend((a, b, c))
    tris.append((i, i + 1, i + 2, color))


def _add_box(verts, tris, x, z, w, d, y0, h, color, roof=(225, 249, 250)):
    """带金属屋顶的玻璃方块，返回四个立面供反光细节复用。"""
    x0, x1 = x - w * 0.5, x + w * 0.5
    z0, z1 = z - d * 0.5, z + d * 0.5
    y1 = y0 + h
    faces = (
        (((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)), (0, 0, 1)),
        (((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)), (0, 0, -1)),
        (((x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)), (1, 0, 0)),
        (((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)), (-1, 0, 0)),
    )
    for points, normal in faces:
        boost = 18 if normal[0] > 0 else (-5 if normal[2] < 0 else 0)
        side = tuple(max(0, min(255, c + boost)) for c in color)
        _emit_quad(verts, tris, points, side, normal)
    _emit_quad(
        verts, tris, ((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)),
        roof, (0, 1, 0),
    )
    return faces


def _add_facade_lines(lines, faces, y0, h):
    """幕墙层线与三道银色竖肋，突出高楼纵向延伸和玻璃反射。"""
    for points, normal in faces:
        y = y0 + 2.8
        while y < y0 + h - 0.18:
            p0 = (points[0][0] + normal[0] * 0.012, y, points[0][2] + normal[2] * 0.012)
            p1 = (points[1][0] + normal[0] * 0.012, y, points[1][2] + normal[2] * 0.012)
            lines.append((p0, p1, normal))
            y += 2.8
        if h > 0.45:
            a, b = points[0], points[1]
            for t in (0.18, 0.50, 0.82):
                gx = a[0] * (1.0-t) + b[0] * t + normal[0] * 0.014
                gz = a[2] * (1.0-t) + b[2] * t + normal[2] * 0.014
                lines.append(((gx, y0 + 0.12, gz), (gx, y0 + h - 0.10, gz), normal))


def _add_cylinder(verts, tris, x, z, y, radius, h, segments, color,
                  top_color=None, top_radius=None):
    """低多边形圆塔 / 圆盘，可通过 top_radius 形成流线收分轮廓。"""
    top_radius = radius if top_radius is None else top_radius
    top_color = color if top_color is None else top_color
    for j in range(segments):
        a0 = math.tau * j / segments
        a1 = math.tau * (j + 1) / segments
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        b0 = (x + c0 * radius, y, z + s0 * radius)
        b1 = (x + c1 * radius, y, z + s1 * radius)
        t0 = (x + c0 * top_radius, y + h, z + s0 * top_radius)
        t1 = (x + c1 * top_radius, y + h, z + s1 * top_radius)
        normal = (math.cos((a0 + a1) * 0.5), 0, math.sin((a0 + a1) * 0.5))
        boost = 12 if j % 3 == 0 else 0
        side = tuple(min(255, c + boost) for c in color)
        _emit_quad(verts, tris, (b0, b1, t1, t0), side, normal)
        _emit_tri(
            verts, tris, ((x, y + h, z), t0, t1), top_color, (0, 1, 0),
        )


def _add_tapered(verts, tris, lines, x, z, w, d, h, color):
    """银色流线收分塔：逐层变窄，楼层色差形成玻璃横带。"""
    floors = max(4, round(h / 2.8))
    for floor in range(floors):
        ya, yb = h * floor / floors, h * (floor + 1) / floors
        ta, tb = 1.0 - 0.36 * ya / h, 1.0 - 0.36 * yb / h
        wa, da = w * ta * 0.5, d * ta * 0.5
        wb, db = w * tb * 0.5, d * tb * 0.5
        faces = (
            (((x-wa, ya, z+da), (x+wa, ya, z+da), (x+wb, yb, z+db), (x-wb, yb, z+db)), (0, 0, 1)),
            (((x+wa, ya, z-da), (x-wa, ya, z-da), (x-wb, yb, z-db), (x+wb, yb, z-db)), (0, 0, -1)),
            (((x+wa, ya, z+da), (x+wa, ya, z-da), (x+wb, yb, z-db), (x+wb, yb, z+db)), (1, 0, 0)),
            (((x-wa, ya, z-da), (x-wa, ya, z+da), (x-wb, yb, z+db), (x-wb, yb, z-db)), (-1, 0, 0)),
        )
        boost = 10 if floor % 2 == 0 else -4
        side = tuple(max(0, min(255, c + boost)) for c in color)
        for points, normal in faces:
            _emit_quad(verts, tris, points, side, normal)
    rw, rd = w * 0.32, d * 0.32
    _emit_quad(
        verts, tris,
        ((x-rw, h, z-rd), (x+rw, h, z-rd), (x+rw, h, z+rd), (x-rw, h, z+rd)),
        (232, 252, 252), (0, 1, 0),
    )
    for sx, sz in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        lines.append((
            (x + sx*w*0.5, 0.05, z + sz*d*0.5),
            (x + sx*rw, h, z + sz*rd),
            (sx * 0.707, 0, sz * 0.707),
        ))


def _add_entrance(verts, tris, lines, x, front_z):
    """人物尺度的双开玻璃入口：侧窗、银框、拉手、灯带和有机雨棚。"""
    silver = (215, 239, 243)
    for side in (-1, 1):
        door_x = x + side * 0.34
        _add_box(verts, tris, door_x, front_z-0.09, 0.64, 0.12, 0.28, 2.12,
                 (48, 143 + side*8, 183 + side*6), roof=(113, 211, 224))
        _add_box(verts, tris, x + side*0.69, front_z-0.12, 0.055, 0.18,
                 0.25, 2.22, silver)
        _add_box(verts, tris, door_x, front_z-0.16, 0.61, 0.035,
                 1.30, 0.045, silver)
        _add_capsule(verts, tris,
                     (x + side*0.13, 1.00, front_z-0.22),
                     (x + side*0.13, 1.43, front_z-0.22),
                     0.026, 6, (235, 252, 250))
        _add_box(verts, tris, x + side*1.08, front_z-0.06, 0.58, 0.12,
                 0.34, 2.04, (105, 199, 218), roof=(180, 234, 236))
        lines.append(((x + side*0.88, 0.55, front_z-0.14),
                      (x + side*1.25, 2.15, front_z-0.14), (0, 0, -1)))
    _add_box(verts, tris, x, front_z-0.12, 0.065, 0.18, 0.25, 2.22, silver)
    for side in (-1, 1):
        _add_box(verts, tris, x + side*1.43, front_z-0.12, 0.13, 0.30,
                 0.20, 2.47, silver)
        _add_capsule(verts, tris,
                     (x + side*1.28, 0.28, front_z-0.79),
                     (x + side*1.28, 2.63, front_z-0.79),
                     0.055, 7, silver)
    _add_box(verts, tris, x, front_z-0.10, 3.00, 0.30, 2.44, 0.18, silver)
    _add_sphere(verts, tris, (x, 2.69, front_z-0.35),
                (1.78, 0.15, 0.91), 18, 6, (239, 253, 248), exponent=0.68)
    _add_capsule(verts, tris, (x-1.47, 2.58, front_z-0.93),
                 (x+1.47, 2.58, front_z-0.93), 0.035, 7, (105, 238, 218))
    for step in range(3):
        _add_box(verts, tris, x, front_z-0.42-step*0.24,
                 2.30+step*0.20, 0.55, step*0.07, 0.07,
                 (193, 225, 228), roof=(239, 253, 248))


def build_city():
    """四种楼型、精细入口、空中连廊和水上生态馆。"""
    verts, tris, colliders, lines, entrances = [], [], [], [], []
    for index, (x, z, w, d, h) in enumerate(CITY):
        x *= CITY_POSITION_SCALE
        z *= CITY_POSITION_SCALE
        w *= CITY_FOOTPRINT_SCALE
        d *= CITY_FOOTPRINT_SCALE
        h *= CITY_HEIGHT_SCALE
        glass = ((80, 174, 214), (112, 200, 226), (76, 158, 204))[index % 3]
        style = index % 4

        # 银色高台基座与可进入的精细玻璃入口。
        podium_w, podium_d = w * 1.08, d * 1.08
        _add_box(verts, tris, x, z, podium_w, podium_d, 0.0, 0.28,
                 (181, 222, 232), roof=(237, 253, 251))
        front_z = z - d * 0.5
        _add_entrance(verts, tris, lines, x, front_z)
        entrances.append((x, front_z-0.10, index))

        if style == 0:  # 阶梯塔：缩进顶层、银色光冠和高耸尖塔
            lower = h * 0.67
            faces = _add_box(verts, tris, x, z, w, d, 0.0, lower, glass)
            _add_facade_lines(lines, faces, 0.0, lower)
            faces = _add_box(verts, tris, x, z, w*0.72, d*0.72, lower, h-lower, glass)
            _add_facade_lines(lines, faces, lower, h-lower)
            _add_sphere(verts, tris, (x, h+0.02, z),
                        (min(w, d)*0.23, 0.22, min(w, d)*0.23), 12, 6,
                        (215, 243, 246), exponent=0.85)
            _add_cylinder(verts, tris, x, z, h+0.08, 0.07,
                          0.85*CITY_HEIGHT_SCALE, 7,
                          (215, 239, 243), top_radius=0.018)

        elif style == 1:  # 收分玻璃塔、银色棱角和两道顶部观景光环
            _add_tapered(verts, tris, lines, x, z, w, d, h, glass)
            for level in (0.78, 0.93):
                halo_r = min(w, d) * 0.5 * (1.0-0.36*level) + 0.11
                _add_cylinder(verts, tris, x, z, h*level, halo_r, 0.12, 12,
                              (208, 236, 241), top_color=(241, 255, 252))
            _add_cylinder(verts, tris, x, z, h+0.02, 0.055, 1.10, 7,
                          (215, 239, 243), top_radius=0.015)

        elif style == 2:  # 圆形观景塔：三道观景环、玻璃穹顶和流线塔身
            radius = min(w, d) * 0.5
            _add_cylinder(verts, tris, x, z, 0.0, radius, h, 14, glass,
                          top_color=(217, 247, 250), top_radius=radius*0.78)
            for level in (0.25, 0.55, 0.82):
                deck_r = radius * (1.0 - 0.22 * level) + 0.13
                _add_cylinder(verts, tris, x, z, h*level, deck_r, 0.15, 14,
                              (211, 239, 242), top_color=(241, 255, 252))
            _add_sphere(verts, tris, (x, h + 0.04, z),
                        (radius*0.72, 0.42, radius*0.72), 14, 8,
                        (197, 239, 247), exponent=0.85)

        else:  # 高层生态露台：三级退台、层间花园与屋顶绿地
            for level in range(3):
                y0 = h * level / 3.0
                level_h = h / 3.0
                scale = 1.0 - level * 0.18
                if level > 0:
                    _add_box(verts, tris, x, z, w*(scale+0.16), d*(scale+0.16),
                             y0+0.015, 0.07, (79, 169, 102), roof=(133, 213, 126))
                faces = _add_box(verts, tris, x, z, w*scale, d*scale,
                                 y0, level_h, glass)
                _add_facade_lines(lines, faces, y0, level_h)
            _add_cylinder(verts, tris, x, z, h + 0.015, min(w, d)*0.25, 0.10, 12,
                          (81, 174, 103), top_color=(128, 211, 123))

        colliders.append((x-podium_w*0.5, z-podium_d*0.5,
                          x+podium_w*0.5, z+podium_d*0.5))

    # 连廊随塔身一同抬高，连接两座前景高楼的中段。
    bridge_y = 3.75 * CITY_HEIGHT_SCALE
    _add_capsule(
        verts, tris,
        (-4.55*CITY_POSITION_SCALE, bridge_y, 18.45*CITY_POSITION_SCALE),
        (-2.20*CITY_POSITION_SCALE, bridge_y, 19.45*CITY_POSITION_SCALE),
        0.55, 8, (205, 243, 247),
    )

    # 参考 oceanscrapers：白色有机水上建筑、银色基座与绿色屋顶。
    px, pz = PONDS[0][0], PONDS[0][1]
    _add_cylinder(verts, tris, px, pz, 0.06, 0.92, 0.30, 16,
                  (184, 225, 232), top_color=(237, 253, 249))
    _add_sphere(verts, tris, (px, 0.73, pz), (1.34, 0.54, 0.94), 20, 10,
                (241, 252, 247), exponent=0.72)
    _add_cylinder(verts, tris, px, pz, 1.13, 0.80, 0.10, 16,
                  (82, 174, 105), top_color=(133, 215, 127))
    _add_sphere(verts, tris, (px, 1.20, pz), (0.82, 0.15, 0.55), 16, 6,
                (128, 211, 123), exponent=0.85)
    colliders.append((px-1.12, pz-0.78, px+1.12, pz+0.78))

    return verts, tris, colliders, lines, entrances


def _add_ring(verts, tris, x, z, y, outer, inner, color, segments=24,
              normal=(0, 1, 0)):
    """水平细环，用于水面涟漪与顶灯。"""
    for j in range(segments):
        a0, a1 = math.tau*j/segments, math.tau*(j+1)/segments
        c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
        _emit_quad(verts, tris, (
            (x+c0*outer, y, z+s0*outer), (x+c1*outer, y, z+s1*outer),
            (x+c1*inner, y, z+s1*inner), (x+c0*inner, y, z+s0*inner),
        ), color, normal)


def _add_plant(verts, tris, x, z):
    """白色水滴花盆与圆润绿叶，呼应 oceanscrapers 的生态细节。"""
    _add_cylinder(verts, tris, x, z, 0.02, 0.66, 0.38, 14,
                  (210, 237, 232), top_color=(246, 255, 248), top_radius=0.54)
    _add_cylinder(verts, tris, x, z, 0.38, 0.52, 0.05, 14,
                  (83, 153, 93), top_color=(113, 183, 102))
    for j in range(4):
        angle = j * 2.4
        lx, lz = x + math.cos(angle)*0.32, z + math.sin(angle)*0.32
        height = 0.93 + (j % 2)*0.30
        _add_capsule(verts, tris, (x, 0.39, z), (lx, height, lz),
                     0.035, 6, (67, 143, 84))
        _add_sphere(verts, tris, (lx, height+0.15, lz),
                    (0.23, 0.42, 0.18), 8, 5,
                    (91+j*7, 174+j*5, 105+j*3), exponent=0.85)


def build_lobby():
    """明亮双层 Aero 大堂：透明幕墙、白色曲线、水景与生态装饰。"""
    verts, tris, colliders = [], [], []
    silver = (202, 229, 232)
    white = (237, 249, 244)

    # 顶篷底面与背面的蓝绿双层玻璃幕墙。
    _emit_quad(verts, tris,
               ((-8, 7.2, -8), (8, 7.2, -8), (8, 7.2, 8), (-8, 7.2, 8)),
               white, (0, -1, 0))
    for i in range(4):
        x0, x1 = -8.0+i*4.0+0.09, -8.0+(i+1)*4.0-0.09
        for y0, y1 in ((0.30, 3.56), (3.76, 7.08)):
            glass = (105+i*7, 199+i*4, 220+i*3, 68)
            _emit_quad(verts, tris,
                       ((x0, y0, 7.96), (x1, y0, 7.96), (x1, y1, 7.96), (x0, y1, 7.96)),
                       glass, (0, 0, -1))
        _add_capsule(verts, tris, (x0+0.25, 0.65, 7.90),
                     (x0+1.15, 3.25, 7.90), 0.022, 6, (213, 250, 247))
    for x in (-8, -4, 0, 4, 8):
        _add_box(verts, tris, x, 8.0, 0.11, 0.18, 0.0, 7.2, silver)
    for y in (0.23, 3.66, 7.14):
        _add_box(verts, tris, 0, 8.0, 16.1, 0.18, y, 0.10, silver)

    # 两侧通透玻璃与细银框，室外天空可穿过玻璃混合显示。
    for side in (-1, 1):
        x = side * 8.0
        for i in range(4):
            z0, z1 = -8.0+i*4.0+0.09, -8.0+(i+1)*4.0-0.09
            for y0, y1 in ((0.30, 3.56), (3.76, 7.08)):
                _emit_quad(verts, tris,
                           ((x, y0, z0), (x, y0, z1), (x, y1, z1), (x, y1, z0)),
                           (100, 204+i*4, 216+i*5, 58), (-side, 0, 0))
        for z in (-8, -4, 0, 4, 8):
            _add_box(verts, tris, x, z, 0.18, 0.11, 0.0, 7.2, silver)
        for y in (0.23, 3.66, 7.14):
            _add_box(verts, tris, x, 0, 0.18, 16.1, y, 0.10, silver)

    # 正面前厅与返回室外的玻璃门。
    for side in (-1, 1):
        _add_box(verts, tris, side*5.0, -8.0, 6.0, 0.24, 0.0, 7.2, white)
        _add_box(verts, tris, side*1.05, -7.94, 0.11, 0.20, 0.0, 2.75, silver)
        _emit_quad(verts, tris,
                   ((side*0.06, 0.12, -7.96), (side*0.96, 0.12, -7.96),
                    (side*0.96, 2.62, -7.96), (side*0.06, 2.62, -7.96)),
                   (91, 185, 207, 74), (0, 0, 1))
    _add_box(verts, tris, 0, -7.94, 2.20, 0.20, 2.67, 0.13, silver)
    _add_sphere(verts, tris, (0, 2.85, -7.82), (1.52, 0.16, 0.52),
                16, 6, white, exponent=0.70)

    # 白色有机柱与分叉柱冠。
    for x in (-5.6, 5.6):
        for z in (-2.7, 3.7):
            _add_cylinder(verts, tris, x, z, 0.02, 0.25, 6.25, 12,
                          (217, 239, 235), top_color=white, top_radius=0.19)
            _add_sphere(verts, tris, (x, 0.18, z), (0.43, 0.18, 0.43),
                        12, 6, white, exponent=0.76)
            _add_capsule(verts, tris, (x, 5.55, z),
                         (x*0.78, 7.08, z+0.65), 0.18, 9, white)
            colliders.append((x-0.34, z-0.34, x+0.34, z+0.34))

    # 圆形顶灯和三条青绿色灯带。
    _add_ring(verts, tris, 0, 1.4, 7.08, 3.20, 3.05, white, normal=(0, -1, 0))
    _add_ring(verts, tris, 0, 1.4, 7.06, 2.82, 2.72,
              (110, 236, 217), normal=(0, -1, 0))
    for z in (-4.6, 1.4, 5.8):
        _add_capsule(verts, tris, (-6.7, 7.02, z), (6.7, 7.02, z),
                     0.045, 7, (140, 244, 228))

    # 中央圆润接待台、蓝绿前面板与银色台面。
    _add_sphere(verts, tris, (0, 0.67, 2.15), (1.95, 0.65, 0.78),
                20, 9, white, exponent=0.66)
    _add_sphere(verts, tris, (0, 0.69, 1.43), (1.38, 0.34, 0.09),
                16, 7, (76, 185, 190), exponent=0.78)
    _add_sphere(verts, tris, (0, 1.23, 2.12), (2.02, 0.10, 0.82),
                20, 5, (224, 246, 242), exponent=0.68)
    _add_capsule(verts, tris, (-1.30, 0.72, 1.33), (1.30, 0.72, 1.33),
                 0.025, 7, (154, 249, 224))
    colliders.append((-2.0, 1.28, 2.0, 3.02))

    # 左侧浅水池与同心涟漪，右侧及后部设置生态绿岛。
    wx, wz = -3.95, 0.35
    _add_cylinder(verts, tris, wx, wz, 0.015, 1.52, 0.12, 24,
                  (195, 228, 227), top_color=white)
    _add_cylinder(verts, tris, wx, wz, 0.135, 1.37, 0.025, 24,
                  (65, 174, 200), top_color=(91, 207, 215))
    for radius in (0.52, 0.94):
        _add_ring(verts, tris, wx, wz, 0.165, radius, radius-0.035,
                  (174, 239, 233))
    _add_sphere(verts, tris, (wx-0.35, 0.28, wz+0.12), (0.48, 0.17, 0.38),
                12, 6, (190, 240, 224), exponent=0.80)
    colliders.append((wx-1.48, wz-1.48, wx+1.48, wz+1.48))
    for px, pz in ((4.35, 0.10), (4.45, 4.65), (-4.60, 5.10)):
        _add_plant(verts, tris, px, pz)
        colliders.append((px-0.64, pz-0.64, px+0.64, pz+0.64))

    # 蓝绿透明隔断，银色边框与白色圆润底座。
    for side in (-1, 1):
        x = side*2.75
        _emit_quad(verts, tris,
                   ((x, 0.28, 4.35), (x, 0.28, 6.55),
                    (x, 3.25, 6.55), (x, 3.25, 4.35)),
                   (80, 204, 192, 82), (-side, 0, 0))
        for z in (4.35, 6.55):
            _add_capsule(verts, tris, (x, 0.12, z), (x, 3.34, z),
                         0.045, 7, silver)
        _add_capsule(verts, tris, (x, 3.32, 4.35), (x, 3.32, 6.55),
                     0.055, 7, white)
        colliders.append((x-0.10, 4.30, x+0.10, 6.60))

    # 墙体与家具碰撞；正门中央保持开放，供返回室外。
    colliders.extend((
        (-8.35, -8.35, -7.90, 8.35), (7.90, -8.35, 8.35, 8.35),
        (-8.35, 7.90, 8.35, 8.35),
        (-8.35, -8.35, -1.0, -7.90), (1.0, -8.35, 8.35, -7.90),
    ))
    return verts, tris, colliders


def resolve_collision(x, z, colliders):
    """将圆形玩家从建筑 AABB 中推出，未压入墙体的方向仍可自由滑动。"""
    radius2 = PLAYER_RADIUS * PLAYER_RADIUS
    for minx, minz, maxx, maxz in colliders:
        cx = min(maxx, max(minx, x))
        cz = min(maxz, max(minz, z))
        dx, dz = x - cx, z - cz
        d2 = dx * dx + dz * dz
        if d2 >= radius2:
            continue
        if d2 > 1e-9:
            distance = math.sqrt(d2)
            push = (PLAYER_RADIUS - distance) / distance
            x += dx * push
            z += dz * push
        else:
            # 圆心位于盒内时，从最近的边推出。
            left, right = x - minx, maxx - x
            near, far = z - minz, maxz - z
            nearest = min(left, right, near, far)
            if nearest == left:
                x = minx - PLAYER_RADIUS
            elif nearest == right:
                x = maxx + PLAYER_RADIUS
            elif nearest == near:
                z = minz - PLAYER_RADIUS
            else:
                z = maxz + PLAYER_RADIUS
    return x, z


# ------------------------------------------------------------------
# 渲染器
# ------------------------------------------------------------------
class Renderer:
    def __init__(self):
        self.tex_levels = build_mips(make_grass_texture())
        self.lobby_tex_levels = build_mips(make_lobby_texture())
        self.sky = make_sky()
        self.sun = make_sun()
        self.sun_r = self.sun.get_width() * 0.5
        self.clouds = make_clouds()
        self.aurora = make_aurora()
        self.rainbow = make_rainbow()
        self.hud = self._make_hud()
        self.lobby_hud = self._make_hud(
            "LOBBY  W/S MOVE  A/D STRAFE  ARROWS LOOK  WALK BACK TO EXIT  ESC QUIT"
        )
        self.toro_verts, self.toro_tris = build_toro_mesh()
        self.face = self._make_face()
        self.shadow = self._make_shadow()
        self.bubble = self._make_bubble()
        city = build_city()
        self.city_verts, self.city_tris, self.colliders, self.city_lines, self.entrances = city
        self.city_shading = self._prepare_shading(self.city_verts, self.city_tris)
        self.lobby_verts, self.lobby_tris, self.lobby_colliders = build_lobby()
        self.lobby_shading = self._prepare_shading(self.lobby_verts, self.lobby_tris)
        self._scale_cache = {}

    @staticmethod
    def _make_face():
        """角色脸部颜文字（作为 3D 头部的贴面）。"""
        font = pygame.font.SysFont("microsoftyahei,simhei,arial", 64, bold=True)
        return font.render("・ω・", False, (40, 40, 54))

    @staticmethod
    def _make_shadow():
        """角色脚下的软阴影。"""
        s = pygame.Surface((64, 20), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 46), (0, 0, 64, 20))
        pygame.draw.ellipse(s, (0, 0, 0, 62), (10, 4, 44, 12))
        return s

    @staticmethod
    def _make_bubble():
        """透明泡泡：淡蓝薄膜、青色轮廓和两处白色高光。"""
        s = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.circle(s, (135, 225, 248, 30), (32, 32), 30)
        pygame.draw.circle(s, (195, 247, 255, 175), (32, 32), 30, 2)
        pygame.draw.arc(s, (255, 255, 255, 225), (8, 7, 45, 45), 1.65, 3.35, 3)
        pygame.draw.arc(s, (255, 174, 219, 120), (5, 5, 54, 54), 3.65, 4.75, 2)
        pygame.draw.arc(s, (255, 241, 143, 130), (6, 6, 52, 52), 0.15, 1.05, 2)
        pygame.draw.circle(s, (255, 255, 255, 205), (20, 17), 4)
        pygame.draw.circle(s, (210, 255, 239, 120), (45, 47), 3)
        return s

    @staticmethod
    def _make_hud(text="W/S MOVE  A/D STRAFE  ARROWS LOOK  SHIFT RUN  DOORS ENTER  ESC QUIT"):
        font = pygame.font.Font(None, 15)
        fg = font.render(text, True, (255, 255, 255))
        sh = font.render(text, True, (20, 40, 70))
        s = pygame.Surface((fg.get_width() + 2, fg.get_height() + 2), pygame.SRCALPHA)
        s.blit(sh, (1, 1))
        s.blit(fg, (0, 0))
        return s

    def _scaled_image(self, source, width, height):
        """缓存整数尺寸的贴面，避免静止或缓慢移动时重复缩放。"""
        key = (id(source), width, height)
        image = self._scale_cache.get(key)
        if image is None:
            if len(self._scale_cache) >= 128:
                self._scale_cache.clear()
            image = pygame.transform.scale(source, (width, height))
            self._scale_cache[key] = image
        return image

    def _ground(self, cam_x, cam_z, yaw, cam_h, horizon, tex_levels=None):
        """向量化 Mode-7 地面，室外草地与大堂水磨石共用采样流程。"""
        levels = self.tex_levels if tex_levels is None else tex_levels
        rows = H - horizon - 1
        dx = np.arange(W, dtype=np.float32) - (W - 1) * 0.5
        dy_all = np.arange(1, rows + 1, dtype=np.float32)

        cy, sy = math.cos(yaw), math.sin(yaw)
        out = np.empty((rows, W, 3), dtype=np.uint8)

        for r0, r1, lvl in MIP_BANDS:
            idx = np.nonzero((dy_all >= r0) & (dy_all < r1))[0]
            if idx.size == 0:
                continue
            tex = levels[lvl]
            size = tex.shape[0]

            dy = dy_all[idx][:, None]                      # (n, 1)
            t = cam_h / dy                                 # 射线参数
            right = dx[None, :] * t                        # (n, W)
            fwd = FOCAL * t

            wx = cam_x + right * cy + fwd * sy
            wz = cam_z - right * sy + fwd * cy

            k = size / TILE_WORLD
            tx = (wx * k).astype(np.int32) % size
            tz = (wz * k).astype(np.int32) % size

            rgb = tex[tz, tx].astype(np.float32)
            fog = np.clip(1.0 - (dy - 1.0) / FOG_DIST, 0.0, 1.0) ** 1.5
            rgb *= (1.0 - fog)[..., None]
            rgb += FOG_COLOR * fog[..., None]
            out[idx] = np.clip(rgb, 0, 255).astype(np.uint8)

        return pygame.surfarray.make_surface(
            np.ascontiguousarray(out.transpose(1, 0, 2))
        )

    def draw(self, frame, cam_x, cam_z, yaw, cam_h, pitch, interior=False):
        # 俯仰：pitch > 0 表示低头；大幅抬头时允许地平线移出画面。
        horizon = max(30, int(HORIZON - pitch))

        frame.blit(self.sky, (0, -SKY_PAD - int(pitch)))

        # 极光：青绿与淡蓝的透明光泽带，和云一样随视角循环移动
        aw = self.aurora.get_width()
        aoff = int(-yaw * SKY_SCALE * 0.55) % aw
        aurora_y = -7 - int(pitch * 0.6)
        frame.blit(self.aurora, (aoff - aw, aurora_y))
        frame.blit(self.aurora, (aoff, aurora_y))

        # 彩虹固定在世界天空中，位于建筑和云层之后的地平线区域
        rainbow_delta = (RAINBOW_AZIMUTH - yaw + math.pi) % math.tau - math.pi
        rainbow_x = W * 0.5 + rainbow_delta * SKY_SCALE
        if -130 < rainbow_x < W + 130:
            frame.blit(self.rainbow, (int(rainbow_x - 130), horizon - 105))

        # 云带：随视角做与转向一致的横向视差滚动（循环平铺）
        cw = self.clouds.get_width()
        off = int(-yaw * SKY_SCALE) % cw
        cloud_y = 4 - int(pitch)
        frame.blit(self.clouds, (off - cw, cloud_y))
        frame.blit(self.clouds, (off, cloud_y))

        # 太阳：按世界方位角投影，转向时会在天空中移动、离开视野
        delta = (SUN_AZIMUTH - yaw + math.pi) % (2.0 * math.pi) - math.pi
        sun_x = W * 0.5 + delta * SKY_SCALE
        sun_y = horizon - SUN_ELEV_PX
        if -self.sun_r < sun_x < W + self.sun_r:
            frame.blit(self.sun, (int(sun_x - self.sun_r), int(sun_y - self.sun_r)))

        if horizon < H - 1:
            levels = self.lobby_tex_levels if interior else self.tex_levels
            frame.blit(
                self._ground(cam_x, cam_z, yaw, cam_h, horizon, levels),
                (0, horizon + 1),
            )
        if interior:
            self._draw_lobby_world(frame, cam_x, cam_z, yaw, cam_h, horizon)
        else:
            self._draw_ponds(frame, cam_x, cam_z, yaw, cam_h, horizon)
            self._draw_world(frame, cam_x, cam_z, yaw, cam_h, horizon)
        hud = self.lobby_hud if interior else self.hud
        frame.blit(hud, (8, H - hud.get_height() - 6))

    @staticmethod
    def _project(x, y, z, cam_x, cam_z, cam_h, horizon, cy, sy):
        """将世界坐标投影到低分辨率屏幕，返回屏幕坐标与深度。"""
        vx, vz = x - cam_x, z - cam_z
        depth = vx * sy + vz * cy
        if depth < NEAR_PLANE:
            return None
        return (
            W * 0.5 + FOCAL * (vx * cy - vz * sy) / depth,
            horizon + FOCAL * (cam_h - y) / depth,
            depth,
        )

    def _draw_ponds(self, frame, cam_x, cam_z, yaw, cam_h, horizon):
        """椭圆水景：白色池沿、深浅水面、同心涟漪和镜面高光。"""
        cy, sy = math.cos(yaw), math.sin(yaw)

        def project(x, y, z):
            return self._project(x, y, z, cam_x, cam_z, cam_h, horizon, cy, sy)

        for x, z, w, d in PONDS:
            angles = [math.tau * i / 28 for i in range(28)]
            outer = [project(x + math.cos(a)*w*0.52, 0.018,
                             z + math.sin(a)*d*0.52) for a in angles]
            inner = [project(x + math.cos(a)*w*0.49, 0.022,
                             z + math.sin(a)*d*0.49) for a in angles]
            if not all(outer) or not all(inner):
                continue
            pygame.draw.polygon(
                frame, (213, 252, 247),
                [(int(p[0]), int(p[1])) for p in outer],
            )
            inner_points = [(int(p[0]), int(p[1])) for p in inner]
            pygame.draw.polygon(frame, (61, 181, 211), inner_points)
            pygame.draw.polygon(frame, (128, 234, 237), inner_points, 1)

            # 水上建筑基座周围的两道涟漪。
            for scale in (0.27, 0.36):
                ripple = [project(x + math.cos(a)*w*scale, 0.028,
                                  z + math.sin(a)*d*scale) for a in angles]
                if all(ripple):
                    pygame.draw.polygon(
                        frame, (143, 229, 234),
                        [(int(p[0]), int(p[1])) for p in ripple], 1,
                    )
            for offset, length in ((-0.26, 0.28), (0.28, 0.22)):
                p0 = project(x - w * length * 0.5, 0.032, z + d * offset)
                p1 = project(x + w * length * 0.5, 0.032, z + d * offset)
                if p0 and p1:
                    pygame.draw.line(
                        frame, (230, 255, 251),
                        (int(p0[0]), int(p0[1])), (int(p1[0]), int(p1[1])),
                    )

    @staticmethod
    def _prepare_shading(verts, tris):
        """城市不会变形，单位法线与固定光照项只需在启动时计算一次。"""
        shading = []
        for ia, ib, ic, _ in tris:
            a, b, c = verts[ia], verts[ib], verts[ic]
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            nx, ny, nz = nx / nl, ny / nl, nz / nl
            diff = nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]
            shading.append((nx, ny, nz, 0.30 * max(diff, 0.0), 0.10 * max(ny, 0.0)))
        return shading

    def _shade_tris(self, verts, tris, cam_x, cam_z, cam_h, horizon, cy, sy,
                    primitives, shading=None):
        """背面与屏幕范围剔除、近裁剪，再计算视角光照和投影。"""
        for tri_index, (ia, ib, ic, col) in enumerate(tris):
            a, b, c = verts[ia], verts[ib], verts[ic]
            adx, adz = a[0] - cam_x, a[2] - cam_z
            bdx, bdz = b[0] - cam_x, b[2] - cam_z
            cdx, cdz = c[0] - cam_x, c[2] - cam_z
            camera = (
                (adx * cy - adz * sy, a[1], adx * sy + adz * cy),
                (bdx * cy - bdz * sy, b[1], bdx * sy + bdz * cy),
                (cdx * cy - cdz * sy, c[1], cdx * sy + cdz * cy),
            )
            ca, cb, cc = camera
            if ca[2] < NEAR_PLANE and cb[2] < NEAR_PLANE and cc[2] < NEAR_PLANE:
                continue

            if shading is None:
                ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
                nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                nx, ny, nz = nx / nl, ny / nl, nz / nl
                diff = nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]
                diffuse, upward = 0.30 * max(diff, 0.0), 0.10 * max(ny, 0.0)
            else:
                nx, ny, nz, diffuse, upward = shading[tri_index]

            vdx, vdy, vdz = cam_x - a[0], cam_h - a[1], cam_z - a[2]
            vlen = math.sqrt(vdx * vdx + vdy * vdy + vdz * vdz) or 1.0
            face_dot = (nx * vdx + ny * vdy + nz * vdz) / vlen
            if face_dot <= 0.0:
                continue

            if ca[2] < NEAR_PLANE or cb[2] < NEAR_PLANE or cc[2] < NEAR_PLANE:
                camera = _clip_near(camera)
                if len(camera) < 3:
                    continue

            # 一次遍历完成投影、深度累加和屏幕包围盒计算。
            projected = []
            depth = 0.0
            min_x = min_y = 1e30
            max_x = max_y = -1e30
            for x, y, z in camera:
                screen_x = W * 0.5 + FOCAL * x / z
                screen_y = horizon + FOCAL * (cam_h - y) / z
                projected.append((screen_x, screen_y))
                depth += z
                min_x = min(min_x, screen_x)
                max_x = max(max_x, screen_x)
                min_y = min(min_y, screen_y)
                max_y = max(max_y, screen_y)
            if max_x < -1.0 or min_x > W + 1.0 or max_y < -1.0 or min_y > H + 1.0:
                continue

            # 保留最初的光照与反射参数，仅缓存不随视角变化的项。
            k = 0.66 + diffuse + 0.14 * face_dot + upward
            depth /= len(projected)
            r, g, b = col[0] * k, col[1] * k, col[2] * k
            if depth > 16.0:
                fog = min((depth - 16.0) / 30.0, 0.85)
                r += (FOG_COLOR[0] - r) * fog
                g += (FOG_COLOR[1] - g) * fog
                b += (FOG_COLOR[2] - b) * fog
            color = (min(255, int(r)), min(255, int(g)), min(255, int(b)))
            points = tuple((int(x), int(y)) for x, y in projected)
            if len(col) == 4:
                primitives.append((depth, "glass", (points, color + (col[3],))))
            else:
                primitives.append((depth, "tri", (points, color)))

    @staticmethod
    def _render_primitives(frame, primitives):
        """按深度绘制统一图元，玻璃使用局部透明表面混合。"""
        primitives.sort(key=lambda p: -p[0])
        for _, kind, data in primitives:
            if kind == "tri":
                points, color = data
                pygame.draw.polygon(frame, color, points)
                pygame.draw.polygon(frame, color, points, 1)
            elif kind == "glass":
                points, color = data
                left = max(0, min(p[0] for p in points))
                right = min(W-1, max(p[0] for p in points))
                top = max(0, min(p[1] for p in points))
                bottom = min(H-1, max(p[1] for p in points))
                if right < left or bottom < top:
                    continue
                glass = pygame.Surface((right-left+1, bottom-top+1), pygame.SRCALPHA)
                local = tuple((x-left, y-top) for x, y in points)
                pygame.draw.polygon(glass, color, local)
                frame.blit(glass, (left, top))
            elif kind == "line":
                p0, p1, color = data
                pygame.draw.line(frame, color, p0, p1)
            elif kind == "ellipse":
                rect, color = data
                pygame.draw.ellipse(frame, color, rect)
            else:
                image, pos = data
                frame.blit(image, pos)

    def _draw_lobby_world(self, frame, cam_x, cam_z, yaw, cam_h, horizon):
        """大堂网格与透明泡泡吊灯，复用城市的光照和深度排序。"""
        cy, sy = math.cos(yaw), math.sin(yaw)
        primitives = []
        self._shade_tris(
            self.lobby_verts, self.lobby_tris,
            cam_x, cam_z, cam_h, horizon, cy, sy, primitives, self.lobby_shading,
        )
        for x, y, z, radius in LOBBY_BUBBLES:
            bp = self._project(x, y, z, cam_x, cam_z, cam_h, horizon, cy, sy)
            if bp is None:
                continue
            size = max(4, int(radius*2.0*FOCAL/bp[2]))
            bubble = self._scaled_image(self.bubble, size, size)
            primitives.append((bp[2], "img", (
                bubble, (int(bp[0]-size*0.5), int(bp[1]-size*0.5)),
            )))
        self._render_primitives(frame, primitives)

    def _draw_world(self, frame, cam_x, cam_z, yaw, cam_h, horizon):
        """统一排序建筑、角色、反光和泡泡，保证前景遮挡关系正确。"""
        cy, sy = math.cos(yaw), math.sin(yaw)

        def project(x, y, z):
            return self._project(x, y, z, cam_x, cam_z, cam_h, horizon, cy, sy)

        primitives = []
        self._shade_tris(
            self.city_verts, self.city_tris,
            cam_x, cam_z, cam_h, horizon, cy, sy, primitives, self.city_shading,
        )

        # 玻璃幕墙的横向层线和竖向高光，背面不绘制。
        for a, b, normal in self.city_lines:
            mx, mz = (a[0] + b[0]) * 0.5, (a[2] + b[2]) * 0.5
            if (cam_x - mx) * normal[0] + (cam_z - mz) * normal[2] <= 0.0:
                continue
            pa, pb = project(*a), project(*b)
            if pa is None or pb is None:
                continue
            depth = (pa[2] + pb[2]) * 0.5 - 0.015
            color = (178, 239, 248)
            if depth > 16.0:
                fog = min((depth - 16.0) / 30.0, 0.85)
                color = tuple(int(c + (FOG_COLOR[i] - c) * fog) for i, c in enumerate(color))
            primitives.append((depth, "line", (
                (int(pa[0]), int(pa[1])), (int(pb[0]), int(pb[1])), color,
            )))

        dx, dz = TORO_X - cam_x, TORO_Z - cam_z
        dist = math.hypot(dx, dz)
        if dist <= 46.0:
            # 模型绕 y 轴面向相机，再转换到世界坐标加入统一队列。
            face = math.atan2(-dx, -dz)
            cf, sf = math.cos(face), math.sin(face)

            def toro_point(x, y, z):
                return (TORO_X + x * cf + z * sf, y, TORO_Z - x * sf + z * cf)

            world_verts = [toro_point(*v) for v in self.toro_verts]
            gp = project(*toro_point(0.0, 0.0, 0.0))
            if gp:
                sw = max(2, int(FOCAL / gp[2]))
                sh = max(1, int(sw * 0.30))
                shadow = self._scaled_image(self.shadow, sw, sh)
                primitives.append((gp[2], "img", (
                    shadow, (int(gp[0] - sw * 0.5), int(gp[1] - sh * 0.5)),
                )))

            self._shade_tris(
                world_verts, self.toro_tris,
                cam_x, cam_z, cam_h, horizon, cy, sy, primitives,
            )

            # 白色耳廓内的淡黄色贴面。
            for side in (-1, 1):
                tri = _ear_tri(side)
                gx = sum(p[0] for p in tri) / 3.0
                gy = sum(p[1] for p in tri) / 3.0
                pts = [project(*toro_point(gx + (x - gx) * 0.62,
                                           gy + (y - gy) * 0.62, 0.056)) for x, y in tri]
                if all(pts):
                    points = tuple((int(p[0]), int(p[1])) for p in pts)
                    depth = sum(p[2] for p in pts) / 3.0 - 0.012
                    primitives.append((depth, "tri", (points, (255, 215, 80))))

            # 粉色脸颊与无括号颜文字。
            for side in (-1, 1):
                cp = project(*toro_point(side * 0.34, 1.46, 0.36))
                if cp:
                    cw = max(2, int(0.20 * FOCAL / cp[2]))
                    ch = max(1, int(cw * 0.58))
                    rect = (int(cp[0] - cw * 0.5), int(cp[1] - ch * 0.5), cw, ch)
                    primitives.append((cp[2] - 0.015, "ellipse", (rect, (237, 157, 164))))

            fp = project(*toro_point(0.0, 1.59, 0.385))
            if fp:
                fw = max(4, int(0.70 * FOCAL / fp[2]))
                fh = max(2, int(fw * self.face.get_height() / self.face.get_width()))
                face_img = self._scaled_image(self.face, fw, fh)
                primitives.append((fp[2] - 0.02, "img", (
                    face_img, (int(fp[0] - fw * 0.5), int(fp[1] - fh * 0.5)),
                )))

        # 带透明薄膜与高光的空气泡泡。
        for x, y, z, radius in BUBBLES:
            bp = project(x, y, z)
            if bp is None:
                continue
            size = max(4, int(radius * 2.0 * FOCAL / bp[2]))
            bubble = self._scaled_image(self.bubble, size, size)
            primitives.append((bp[2], "img", (
                bubble, (int(bp[0] - size * 0.5), int(bp[1] - size * 0.5)),
            )))

        self._render_primitives(frame, primitives)


# ------------------------------------------------------------------
# 主循环
# ------------------------------------------------------------------
def main():
    pygame.init()
    pygame.display.set_caption("PS3 Pixel Walker - Frutiger Aero")
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    clock = pygame.time.Clock()

    frame = pygame.Surface((W, H))
    renderer = Renderer()

    cam_x = cam_z = 0.0
    yaw = 0.0
    pitch = 0.0
    bob = 0.0
    fps_timer = 0.0
    last_view = None
    scene = "city"
    current_building = 0

    running = True
    while running:
        dt = min(clock.tick(60) / 1000.0, 0.05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        keys = pygame.key.get_pressed()

        # ---- 方向键控制视角 ----
        yaw += (keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]) * TURN_SPEED * dt
        pitch += (keys[pygame.K_DOWN] - keys[pygame.K_UP]) * PITCH_SPEED * dt
        pitch = max(-PITCH_MAX, min(PITCH_MAX, pitch))

        # ---- WASD 控制移动：W 前进 / S 后退 / D 右移 / A 左移 ----
        fwd = keys[pygame.K_w] - keys[pygame.K_s]
        side = keys[pygame.K_d] - keys[pygame.K_a]
        if fwd or side:
            length = math.hypot(fwd, side)
            fwd /= length
            side /= length
            speed = RUN_SPEED if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) else MOVE_SPEED
            # 前向向量 (sin, cos)，右向向量 (cos, -sin)
            cam_x += (math.sin(yaw) * fwd + math.cos(yaw) * side) * speed * dt
            cam_z += (math.cos(yaw) * fwd - math.sin(yaw) * side) * speed * dt
            colliders = renderer.lobby_colliders if scene == "lobby" else renderer.colliders
            cam_x, cam_z = resolve_collision(cam_x, cam_z, colliders)
            bob += dt * 9.0

        # 走近任意正门即进入大堂；穿过大堂前门则回到原建筑门外。
        if scene == "city":
            for entrance_index, (door_x, door_z, _) in enumerate(renderer.entrances):
                if abs(cam_x-door_x) < 0.95 and door_z-1.15 < cam_z < door_z+0.05:
                    scene = "lobby"
                    current_building = entrance_index
                    cam_x, cam_z = 0.0, -5.8
                    yaw = pitch = 0.0
                    break
        elif cam_z < -7.25 and abs(cam_x) < 0.60:
            scene = "city"
            door_x, door_z, _ = renderer.entrances[current_building]
            cam_x, cam_z = door_x, door_z-1.25
            yaw, pitch = math.pi, 0.0

        cam_h = CAM_H + math.sin(bob) * 0.045

        view = (scene, cam_x, cam_z, yaw, pitch, cam_h)
        if view != last_view:
            renderer.draw(
                frame, cam_x, cam_z, yaw, cam_h, pitch,
                interior=(scene == "lobby"),
            )
            last_view = view
        pygame.transform.scale(frame, (WIN_W, WIN_H), screen)
        pygame.display.flip()

        fps_timer += dt
        if fps_timer > 0.5:
            fps_timer = 0.0
            location = "Aero Lobby" if scene == "lobby" else "Frutiger Aero"
            pygame.display.set_caption(
                f"PS3 Pixel Walker - {location}   |   {clock.get_fps():.0f} FPS"
            )

    pygame.quit()


if __name__ == "__main__":
    main()
