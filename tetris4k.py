import pygame
import random
import sys
import math
import numpy as np

# Stereo — matches synthesized buffers
pygame.mixer.pre_init(22050, -16, 2, 512)
pygame.init()
pygame.mixer.init()

# === Layout: Game Boy-ish playfield scale in a 600×400 window ===
WINDOW_W = 600
WINDOW_H = 400
COLS = 10
ROWS = 20
CELL = WINDOW_H // ROWS  # 400 / 20 = 20 px (matches GB block aspect in this window)
PLAYFIELD_W = COLS * CELL
SIDE_X = PLAYFIELD_W
SIDE_W = WINDOW_W - PLAYFIELD_W

screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
pygame.display.set_caption("AC'S TETRIS")

clock = pygame.time.Clock()
logo_font = pygame.font.SysFont("consolas", 40, bold=True)
font = pygame.font.SysFont("consolas", 22, bold=True)
small_font = pygame.font.SysFont("consolas", 16)

BLACK = (0, 0, 0)
GRAY = (30, 30, 30)
WHITE = (255, 255, 255)

COLORS = [
    (15, 56, 15),      # GB-style green palette approx (I-type)
    (48, 98, 48),
    (77, 130, 47),
    (104, 160, 60),
    (139, 195, 74),
    (172, 220, 100),
    (198, 240, 120),
]

SHAPES = [
    [[1, 1, 1, 1]],
    [[1, 1], [1, 1]],
    [[0, 1, 0], [1, 1, 1]],
    [[0, 1, 1], [1, 1, 0]],
    [[1, 1, 0], [0, 1, 1]],
    [[1, 0, 0], [1, 1, 1]],
    [[0, 0, 1], [1, 1, 1]],
]

NOTE_FREQS = {
    "A4": 440.00, "Bb4": 466.16, "B4": 493.88, "C5": 523.25, "Db5": 554.37,
    "D5": 587.33, "Eb5": 622.25, "E5": 659.25, "F5": 698.46, "Gb5": 739.99,
    "G5": 783.99, "A5": 880.00, "Bb5": 932.33, "G4": 392.00, "E4": 329.63,
}

# Authentic GB-style gravity: frames per 1-cell drop (LCD ~59.73 Hz — we simulate at 60 Hz)
FRAME_MS = 1000.0 / 60.0
# Level 0..20 inclusive (classic A-type progression by lines / 10)
LEVEL_DROP_FRAMES = [
    53, 49, 45, 41, 37, 33, 28, 22, 17, 11, 10,
    10, 9, 9, 8, 8, 7, 7, 6, 5, 3,
]


def gb_drop_interval_ms(level: int, soft_drop: bool) -> float:
    lv = max(0, min(level, 20))
    f = LEVEL_DROP_FRAMES[lv]
    if soft_drop:
        f = max(3.0, f / 2.0)  # ~GB soft-slide (roughly halves frame delay)
    return float(f * FRAME_MS)


# Korobeiniki Theme A — core cheerful loop only (drops the improvised bridge that read as “sad” / off-key)
GB_BPM = 160
EIGHTH_MS = int(60000 / GB_BPM / 2)


def _stretch(notes_raw):
    return [(n, u * EIGHTH_MS) for n, u in notes_raw]


MELODY_RAW_REPEAT = (
    [
        ("E5", 1), ("B4", 1), ("C5", 1), ("D5", 1), ("E5", 1), ("D5", 1), ("C5", 1), ("B4", 1),
        ("A4", 1), ("A4", 1), ("C5", 1), ("E5", 1), ("E5", 1), ("D5", 1), ("C5", 1), ("B4", 2),
        ("C5", 1), ("D5", 1), ("E5", 1), ("C5", 1), ("A4", 1), ("A4", 1), ("A4", 1), ("B4", 1),
        ("C5", 1), ("D5", 1), ("E5", 1), ("D5", 1), ("C5", 1), ("B4", 1), ("A4", 2), ("A4", 2),
        ("E5", 1), ("E5", 1), ("E5", 1), ("C5", 1), ("D5", 1), ("E5", 1), ("D5", 1), ("C5", 1),
        ("B4", 1), ("B4", 1), ("C5", 1), ("D5", 1), ("E5", 1), ("C5", 1), ("A4", 1), ("A4", 2),
    ]
    * 2
)

MELODY = _stretch(MELODY_RAW_REPEAT)

# Game Over “sad sting” (~GB Game Over motif: slide down home)
GAME_OVER_RAW = [
    ("E5", 2), ("D5", 2), ("C5", 2), ("B4", 2), ("A4", 2), ("G4", 2), ("E4", 6),
]


def synthesize_piece(freq, duration_ms, volume=0.55, sample_rate=22050):
    """Square wave lead (GB pulse feel). freq <= 0 = silence/rest."""
    if duration_ms <= 0:
        return np.zeros(0, dtype=np.int16)
    ns = max(1, int(sample_rate * duration_ms / 1000))
    if freq <= 0:
        return np.zeros(ns, dtype=np.int16)
    t = np.linspace(0, duration_ms / 1000, ns, endpoint=False)
    wave = volume * np.sign(np.sin(2 * math.pi * freq * t))
    return (wave * 32767).astype(np.int16)


def build_sound(note_events, eighth_ms=EIGHTH_MS, gap_fac=0.006):
    sample_rate = 22050
    buf = np.array([], dtype=np.int16)
    gap = np.zeros(max(1, int(sample_rate * gap_fac)), dtype=np.int16)
    for sym, beats in note_events:
        if sym == "-" or sym is None:
            dur = eighth_ms * beats
            buf = np.concatenate((buf, synthesize_piece(0.0, dur, sample_rate=sample_rate)))
        else:
            dur = eighth_ms * beats
            fq = NOTE_FREQS.get(sym, 440)
            buf = np.concatenate((buf, synthesize_piece(fq, dur, sample_rate=sample_rate)))
        buf = np.concatenate((buf, gap))
    stereo = np.column_stack((buf, buf))
    return pygame.mixer.Sound(buffer=stereo)


def build_theme_from_pairs(pairs_ms):
    sample_rate = 22050
    buf = np.array([], dtype=np.int16)
    gap = np.zeros(max(1, int(sample_rate * 0.006)), dtype=np.int16)
    for note, dur in pairs_ms:
        fq = NOTE_FREQS.get(note, 440)
        buf = np.concatenate((buf, synthesize_piece(fq, float(dur), sample_rate=sample_rate)))
        buf = np.concatenate((buf, gap))
    stereo = np.column_stack((buf, buf))
    return pygame.mixer.Sound(buffer=stereo)


GAME_OVER_SOUND = build_sound(GAME_OVER_RAW, eighth_ms=int(EIGHTH_MS * 0.9))
TETRIS_MUSIC = build_theme_from_pairs(MELODY)

music_playing = False


class Tetromino:
    def __init__(self):
        self.type = random.randint(0, 6)
        self.shape = [row[:] for row in SHAPES[self.type]]
        self.color_idx = min(self.type, len(COLORS) - 1)
        self.x = COLS // 2 - len(self.shape[0]) // 2
        self.y = 0


def rotate_cw(matrix):
    return [list(row) for row in zip(*matrix[::-1])]


def rotate_ccw(matrix):
    """90° CCW = three 90° CW steps (handles rectangular mino matrices)."""
    return rotate_cw(rotate_cw(rotate_cw(matrix)))


def valid_move(board, piece_shape, px, py):
    for i, row in enumerate(piece_shape):
        for j, cell in enumerate(row):
            if cell:
                nx = px + j
                ny = py + i
                if nx < 0 or nx >= COLS or ny >= ROWS:
                    return False
                if ny >= 0 and board[ny][nx]:
                    return False
    return True


def try_rotate(board, piece, cw=True):
    if piece.type == 1:  # O — noop on GB
        return False
    nxt = rotate_cw(piece.shape) if cw else rotate_ccw(piece.shape)
    kicks = [(0, 0), (-1, 0), (1, 0), (-2, 0), (2, 0)]  # light wall-kick shim (PC port)
    for kx, ky in kicks:
        if valid_move(board, nxt, piece.x + kx, piece.y + ky):
            piece.shape = nxt
            piece.x += kx
            piece.y += ky
            return True
    return False

def gb_line_score(level: int, nlines: int) -> int:
    if nlines <= 0:
        return 0
    mult = level + 1
    pts = [0, 40, 100, 300, 1200][nlines]
    return mult * pts


def apply_piece_lock(board, piece, next_piece, lines_before_lock: int):
    """
    Weld piece to board and clear rows. Uses Game Boy multiplier with level BEFORE the clear.
    Returns (score_added, cleared_lines_count, alive, new_piece, new_next_piece).
    """
    lvl_for_score = min(20, lines_before_lock // 10)
    for i, row in enumerate(piece.shape):
        for j, cell in enumerate(row):
            if cell and piece.y + i >= 0:
                board[piece.y + i][piece.x + j] = piece.type + 1

    yi = ROWS - 1
    nclear = 0
    while yi >= 0:
        if all(board[yi]):
            del board[yi]
            board.insert(0, [0] * COLS)
            nclear += 1
        else:
            yi -= 1

    sc = gb_line_score(lvl_for_score, nclear)
    alive = False
    new_piece = next_piece
    new_next_piece = Tetromino()
    if valid_move(board, new_piece.shape, new_piece.x, new_piece.y):
        alive = True
    return sc, nclear, alive, new_piece, new_next_piece


def draw_menu():
    screen.fill(BLACK)
    logo = logo_font.render("AC'S TETRIS", True, WHITE)
    screen.blit(logo, logo.get_rect(center=(WINDOW_W // 2, 110)))

    items = ["PLAY GAME", "HOW TO PLAY", "ABOUT", "SOUND SETTINGS", "EXIT"]
    y0 = 190
    for i, label in enumerate(items):
        hue = (255, 220, 0) if i == selected_menu else WHITE
        t = font.render(label, True, hue)
        screen.blit(t, t.get_rect(center=(WINDOW_W // 2, y0 + i * 36)))

    foot = small_font.render("60 FPS • Gravity & score per Game Boy Tetris", True, (110, 110, 110))
    screen.blit(foot, foot.get_rect(center=(WINDOW_W // 2, WINDOW_H - 26)))


def draw_howto():
    screen.fill(BLACK)
    title = logo_font.render("HOW TO PLAY", True, WHITE)
    screen.blit(title, title.get_rect(center=(WINDOW_W // 2, 40)))
    lines = [
        "←→ move   DAS repeats like GB/NES",
        "↓ soft drop (~5× faster lock)",
        "Z / ↑ rotate CW    X rotate CCW",
        "SPACE sonic drop",
        "",
        "Level every 10 lines (max level 20).",
        "ESCAPE during play: main menu (stops engine).",
        "ENTER / ESCAPE: return from this screen.",
    ]
    y = 100
    for line in lines:
        screen.blit(small_font.render(line, True, WHITE), (40, y))
        y += 26


def draw_about():
    screen.fill(BLACK)
    screen.blit(
        logo_font.render("ABOUT", True, WHITE),
        logo_font.render("ABOUT", True, WHITE).get_rect(center=(WINDOW_W // 2, 40)),
    )
    blob = (
        "AC'S TETRIS — Gravity table, +1 level per 10 lines,",
        "and (Lv+1)×{40,100,300,1200} scoring like Game Boy Tetris.",
        "Theme A loop (no improvised bridge); Game Over jingle.",
        "",
        "Press ENTER / ESCAPE to return.",
    )
    y = 100
    for line in blob:
        screen.blit(small_font.render(line, True, WHITE), (40, y))
        y += 28


def draw_sound_settings():
    screen.fill(BLACK)
    screen.blit(logo_font.render("SOUND", True, WHITE), (40, 40))
    st = "ON" if music_enabled else "OFF"
    screen.blit(font.render(f"Theme A (in-game): {st} — SPACE toggle", True, WHITE), (40, 110))
    screen.blit(
        small_font.render(
            "Theme A only during play. Game Over sting once (never on menu).",
            True,
            (170, 170, 170),
        ),
        (40, 150),
    )
    screen.blit(small_font.render("ENTER or ESCAPE: back", True, WHITE), (40, 210))


def main():
    global selected_menu, music_enabled, music_playing
    pygame.key.set_repeat(0)  # we use manual DAS
    selected_menu = 0
    music_enabled = True
    music_playing = False

    game_state = "menu"  # menu, game, howto, about, settings, game_over
    go_timer = 0.0

    board = [[0] * COLS for _ in range(ROWS)]
    piece = Tetromino()
    next_piece = Tetromino()
    score = lines_total = level = 0
    fall_timer = 0.0
    soft_drop = False
    das_l = das_r = 0.0
    DAS_INIT = float(13 * FRAME_MS)
    DAS_REP = float(7 * FRAME_MS)

    def go_main_menu_stop_engine():
        """Leave play / game-over: main menu, silence audio, reset sim state (engine off)."""
        global music_playing
        nonlocal game_state, board, piece, next_piece, score, lines_total, level
        nonlocal fall_timer, das_l, das_r, soft_drop, go_timer
        TETRIS_MUSIC.stop()
        GAME_OVER_SOUND.stop()
        music_playing = False
        go_timer = 0.0
        fall_timer = 0.0
        das_l = das_r = 0.0
        soft_drop = False
        game_state = "menu"
        board = [[0] * COLS for _ in range(ROWS)]
        piece = Tetromino()
        next_piece = Tetromino()
        score = lines_total = level = 0

    running = True
    while running:
        dt = clock.tick(60)
        down_keys = pygame.key.get_pressed()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if game_state == "menu":
                    if event.key == pygame.K_UP:
                        selected_menu = (selected_menu - 1) % 5
                    if event.key == pygame.K_DOWN:
                        selected_menu = (selected_menu + 1) % 5
                    if event.key == pygame.K_RETURN:
                        if selected_menu == 0:
                            game_state = "game"
                            board = [[0] * COLS for _ in range(ROWS)]
                            piece = Tetromino()
                            next_piece = Tetromino()
                            score = lines_total = level = 0
                            fall_timer = 0.0
                            das_l = das_r = 0.0
                            music_playing = False
                            soft_drop = False
                            go_timer = 0.0
                        elif selected_menu == 1:
                            game_state = "howto"
                        elif selected_menu == 2:
                            game_state = "about"
                        elif selected_menu == 3:
                            game_state = "settings"
                        elif selected_menu == 4:
                            running = False

                elif game_state == "game":
                    if event.key == pygame.K_z or event.key == pygame.K_UP:
                        try_rotate(board, piece, cw=True)
                    if event.key == pygame.K_x:
                        try_rotate(board, piece, cw=False)
                    if event.key == pygame.K_SPACE:
                        while valid_move(board, piece.shape, piece.x, piece.y + 1):
                            piece.y += 1
                        sc_a, clr, alive, piece, next_piece = apply_piece_lock(
                            board, piece, next_piece, lines_total,
                        )
                        score += sc_a
                        lines_total += clr
                        level = min(20, lines_total // 10)
                        fall_timer = 0.0
                        if not alive:
                            if music_playing:
                                TETRIS_MUSIC.stop()
                                music_playing = False
                            if music_enabled:
                                GAME_OVER_SOUND.play()
                            game_state = "game_over"
                            go_timer = 2600.0
                            lv = min(20, lines_total // 10)
                            print(f"\nGAME OVER — score {score}, lines {lines_total}, lv {lv}")
                    if event.key == pygame.K_ESCAPE:
                        go_main_menu_stop_engine()

                elif game_state == "game_over":
                    if event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                        go_main_menu_stop_engine()

                elif game_state == "settings":
                    if event.key == pygame.K_SPACE:
                        music_enabled = not music_enabled
                    elif event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                        game_state = "menu"

                elif game_state in ("howto", "about"):
                    if event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                        game_state = "menu"

        # Theme A (OST): only during active gameplay — never menu, help, settings, or game-over
        if game_state != "game":
            TETRIS_MUSIC.stop()
            music_playing = False

        soft_drop = down_keys[pygame.K_DOWN] if game_state == "game" else False

        if game_state == "game":
            # BGM — start only here; all other screens silence the OST above
            if music_enabled and not music_playing:
                TETRIS_MUSIC.play(-1)
                music_playing = True
            if not music_enabled and music_playing:
                TETRIS_MUSIC.stop()
                music_playing = False

            lvl = min(20, lines_total // 10)
            level = lvl
            iv = gb_drop_interval_ms(level, soft_drop)

            if down_keys[pygame.K_LEFT]:
                if das_l == 0.0:
                    if valid_move(board, piece.shape, piece.x - 1, piece.y):
                        piece.x -= 1
                    das_l = DAS_INIT
                else:
                    das_l -= dt
                    while das_l <= 0:
                        if valid_move(board, piece.shape, piece.x - 1, piece.y):
                            piece.x -= 1
                        das_l += DAS_REP
            else:
                das_l = 0.0

            if down_keys[pygame.K_RIGHT]:
                if das_r == 0.0:
                    if valid_move(board, piece.shape, piece.x + 1, piece.y):
                        piece.x += 1
                    das_r = DAS_INIT
                else:
                    das_r -= dt
                    while das_r <= 0:
                        if valid_move(board, piece.shape, piece.x + 1, piece.y):
                            piece.x += 1
                        das_r += DAS_REP
            else:
                das_r = 0.0

            fall_timer += dt
            while fall_timer >= iv:
                fall_timer -= iv
                if valid_move(board, piece.shape, piece.x, piece.y + 1):
                    piece.y += 1
                else:
                    sc_a, clr, alive, piece, next_piece = apply_piece_lock(
                        board, piece, next_piece, lines_total,
                    )
                    score += sc_a
                    lines_total += clr
                    lvl = min(20, lines_total // 10)
                    level = lvl
                    fall_timer = 0.0
                    if not alive:
                        if music_playing:
                            TETRIS_MUSIC.stop()
                            music_playing = False
                        if music_enabled:
                            GAME_OVER_SOUND.play()
                        game_state = "game_over"
                        go_timer = 2600.0
                        lv = min(20, lines_total // 10)
                        print(f"\nGAME OVER — score {score}, lines {lines_total}, lv {lv}")
                    break

        elif game_state == "game_over":
            go_timer -= dt
            if go_timer <= 0:
                go_main_menu_stop_engine()

        screen.fill(BLACK)

        if game_state == "menu":
            draw_menu()
        elif game_state == "howto":
            draw_howto()
        elif game_state == "about":
            draw_about()
        elif game_state == "settings":
            draw_sound_settings()
        else:
            # playfield GB green wash
            gb_bg = (15, 48, 15)
            pygame.draw.rect(screen, gb_bg, (0, 0, PLAYFIELD_W, WINDOW_H))
            for gy in range(ROWS):
                for gx in range(COLS):
                    if board[gy][gx]:
                        cid = board[gy][gx] - 1
                        col = COLORS[cid % len(COLORS)]
                        pygame.draw.rect(screen, col, (gx * CELL, gy * CELL, CELL - 1, CELL - 1))

            for i, row in enumerate(piece.shape):
                for j, cell in enumerate(row):
                    if cell and game_state != "game_over":
                        c = COLORS[piece.color_idx]
                        pygame.draw.rect(
                            screen, c,
                            ((piece.x + j) * CELL + 1, (piece.y + i) * CELL + 1, CELL - 3, CELL - 3),
                        )

            pygame.draw.rect(screen, GRAY, (SIDE_X, 0, SIDE_W, WINDOW_H))
            oy = 16
            screen.blit(font.render("SCORE", True, WHITE), (SIDE_X + 14, oy))
            screen.blit(font.render(str(score), True, WHITE), (SIDE_X + 14, oy + 28))
            screen.blit(font.render(f"LINES {lines_total}", True, WHITE), (SIDE_X + 14, oy + 72))
            screen.blit(font.render(f"LV {level}", True, (170, 255, 170)), (SIDE_X + 14, oy + 110))
            ps = CELL // 2
            pygame.draw.rect(screen, BLACK, (SIDE_X + 12, oy + 150, SIDE_W - 24, ps * (len(next_piece.shape) + 1) + 20))
            screen.blit(font.render("NEXT", True, WHITE), (SIDE_X + 14, oy + 140))
            for i, prow in enumerate(next_piece.shape):
                for j, c in enumerate(prow):
                    if c:
                        cc = COLORS[next_piece.color_idx]
                        pygame.draw.rect(
                            screen, cc,
                            (SIDE_X + 40 + j * ps, oy + 180 + i * ps, ps - 1, ps - 1),
                        )

            screen.blit(
                small_font.render("Z/↑ X  SPACE  ←→↓ DAS  ESC=menu", True, (160, 160, 160)),
                (SIDE_X + 14, WINDOW_H - 28),
            )

            if game_state == "game_over":
                tint = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
                tint.fill((0, 0, 0, 160))
                screen.blit(tint, (0, 0))
                go = logo_font.render("GAME OVER", True, (255, 80, 80))
                screen.blit(go, go.get_rect(center=(WINDOW_W // 2, WINDOW_H // 2 - 26)))
                kk = small_font.render("ENTER / ESC — menu", True, WHITE)
                screen.blit(kk, kk.get_rect(center=(WINDOW_W // 2, WINDOW_H // 2 + 20)))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
