# ruff: noqa
"""Pond AUC with the background matched to the position of the pond, bootstrap CI by pond, ten seeds, and the "pit" measure of the app.

Run: cd scripts/ponds_matched && ../../.venv/bin/python fetch_data.py && ../../.venv/bin/python honest.py (network, a few minutes).
Result 22.11.2026: AUC 0.858 (95%: 0.826-0.886), 120 ponds from 50 parcels; the pit rule of the app AUC 0.53.
"""

import json
import random
import time
import zlib

import numpy as np
from common import W, load_samples, load_script
from scipy.ndimage import distance_transform_edt
from scipy.signal import convolve2d
from scipy.stats import rankdata

ep = load_script("eval_ponds")
SEED0 = ep.SEED
PER_POND, BG_PER_POND, HALF = 5, 10, 5
BAND_M, BUF_LO, BUF_HI = 2.0, 30.0, 150.0
N_BOOT, N_SEEDS = 1000, 10
PIT_MIN = 0.2  # próg z katalogu (niecka-przy-wyplywie), użyty także w aplikacji jako domyślny


def auc_fast(pos, neg):
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    r = rankdata(np.concatenate([pos, neg]))
    return (r[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def depth_all(z):
    """Głębokość każdej komórki pod płaszczyzną dopasowaną w oknie 11x11 (tak jak eval_ponds), wektorowo."""
    known = np.isfinite(z)
    zz = np.where(known, z, 0.0)
    K = known.astype(float)
    I, J = np.indices(z.shape).astype(float)
    ones = np.ones((2 * HALF + 1, 2 * HALF + 1))
    cv = lambda a: convolve2d(a, ones, mode="same")
    n, Si, Sj = cv(K), cv(I * K), cv(J * K)
    Sii, Sij, Sjj = cv(I * I * K), cv(I * J * K), cv(J * J * K)
    Sz, Siz, Sjz = cv(zz), cv(I * zz), cv(J * zz)
    A = np.stack([np.stack([Sii, Sij, Si], -1), np.stack([Sij, Sjj, Sj], -1), np.stack([Si, Sj, n], -1)], -2)
    b = np.stack([Siz, Sjz, Sz], -1)
    ok = known & (n >= ep.MIN_WINDOW_CELLS)
    det = np.linalg.det(A)
    ok &= np.abs(det) > 1e-6
    A[~ok] = np.eye(3)
    sol = np.linalg.solve(A, b[..., None])[..., 0]
    out = sol[..., 0] * I + sol[..., 1] * J + sol[..., 2] - z
    out[~ok] = np.nan
    return out


def pit_all(z):
    """Głębokość dołka (niższa od 8 sąsiadów, wszyscy znani) w m; 0, gdy komórka nie jest dołkiem; NaN poza znanymi."""
    R, C = z.shape
    pad = np.full((R + 2, C + 2), np.nan)
    pad[1:-1, 1:-1] = z
    nb = np.stack(
        [
            pad[1 + dr : 1 + dr + R, 1 + dc : 1 + dc + C]
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if (dr, dc) != (0, 0)
        ]
    )
    allk = np.isfinite(nb).all(0) & np.isfinite(z)
    low = np.where(allk, nb.min(0), np.nan)
    with np.errstate(invalid="ignore"):
        d = np.where(allk & (z < low), low - z, 0.0)
    d[~np.isfinite(z)] = np.nan
    return d


def verify(samples):
    """Zgodność wektorowej miary z eval_ponds.depth_below_plane na kilku komórkach."""
    grid = samples[0][0]
    z = np.array(grid.z, dtype=float).reshape(grid.rows, grid.cols)
    D = depth_all(z)
    rng = random.Random(1)
    diffs = []
    for _ in range(40):
        r, c = rng.randrange(grid.rows), rng.randrange(grid.cols)
        ref = ep.depth_below_plane(grid, z, r, c)
        if ref is None:
            assert not np.isfinite(D[r, c]) or True
            continue
        diffs.append(abs(ref - D[r, c]))
    return float(np.nanmax(diffs)), len(diffs)


def prep(samples):
    """Dla każdej siatki: z, maski zbiorników, głębokości, dołki."""
    out = []
    for k, (grid, ponds) in enumerate(samples):
        if grid is None or not ponds:
            continue
        z = np.array(grid.z, dtype=float).reshape(grid.rows, grid.cols)
        known = np.isfinite(z)
        masks = [ep.pond_mask(grid, [o]) & known for o in ponds]
        masks = [m for m in masks if m.any()]
        if not masks:
            continue
        allp = ep.pond_mask(grid, ponds)
        out.append(
            dict(
                k=k,
                step=grid.step_m,
                z=z,
                known=known,
                allp=allp,
                masks=masks,
                depth=depth_all(z),
                pit=pit_all(z),
            )
        )
    return out


def bg_pool(g, m, variant):
    pool = g["known"] & ~g["allp"]
    zp = float(np.median(g["z"][m]))
    if variant in ("band", "both"):
        pool = pool & (np.abs(g["z"] - zp) <= BAND_M)
    if variant in ("buffer", "both"):
        dist = distance_transform_edt(~m) * g["step"]
        pool = pool & (dist >= BUF_LO) & (dist <= BUF_HI)
    return pool


VARIANTS = {
    "grid": "tło: cała siatka (jak oryginał)",
    "band": "tło: ta sama wysokość ±2 m od lustra zbiornika",
    "buffer": "tło: pas 30–150 m od brzegu zbiornika",
    "both": "tło: pas wysokości ±2 m ORAZ pas 30–150 m",
}


def draw(rng, mask, n):
    r, c = np.nonzero(mask)
    idx = rng.sample(range(len(r)), min(n, len(r)))
    return [(int(r[i]), int(c[i])) for i in idx]


def build(prepped, variant, seed):
    """Lista zbiorników: każdy z wynikami miar (depth, pit) dla komórek zbiornika i tła."""
    items = []
    for g in prepped:
        for j, m in enumerate(g["masks"]):
            pool = bg_pool(g, m, variant)
            if not pool.any():
                items.append(dict(k=g["k"], ncell=int(m.sum()), empty=True))
                continue
            rng = random.Random(seed + zlib.crc32(f"{g['k']}:{j}".encode()))
            pc, nc = draw(rng, m, PER_POND), draw(rng, pool, BG_PER_POND)
            get = lambda cells, key: np.array([g[key][r, c] for r, c in cells], float)
            pit_all_cells = g["pit"][m]
            items.append(
                dict(
                    k=g["k"],
                    ncell=int(m.sum()),
                    empty=False,
                    pd=get(pc, "depth"),
                    nd=get(nc, "depth"),
                    pp=get(pc, "pit"),
                    np_=get(nc, "pit"),
                    has_pit=bool(np.nanmax(pit_all_cells) > 0),
                    has_pit20=bool(np.nanmax(pit_all_cells) >= PIT_MIN),
                    pit_share_all=float(np.nanmean(pit_all_cells > 0)),
                    pit20_share_all=float(np.nanmean(pit_all_cells >= PIT_MIN)),
                )
            )
    return [i for i in items if not i["empty"]], sum(i["empty"] for i in items)


def pooled(items, pk, nk):
    p = np.concatenate([i[pk] for i in items])
    n = np.concatenate([i[nk] for i in items])
    return p[np.isfinite(p)], n[np.isfinite(n)]


def boot(items, pk, nk, rng, by="pond"):
    if by == "pond":
        groups = [[i] for i in items]
    else:
        d = {}
        for i in items:
            d.setdefault(i["k"], []).append(i)
        groups = list(d.values())
    vals = []
    for _ in range(N_BOOT):
        pick = [groups[x] for x in rng.integers(0, len(groups), len(groups))]
        sel = [i for grp in pick for i in grp]
        p, n = pooled(sel, pk, nk)
        v = auc_fast(p, n)
        if np.isfinite(v):
            vals.append(v)
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def main():
    t0 = time.time()
    samples = load_samples()
    print("próbek:", len(samples), flush=True)
    err, nchk = verify(samples)
    print(
        f"zgodność miary wektorowej z depth_below_plane: max różnica {err:.2e} m na {nchk} komórkach",
        flush=True,
    )
    prepped = prep(samples)
    print(
        f"siatek z zbiornikami: {len(prepped)}, zbiorników: {sum(len(g['masks']) for g in prepped)}, {time.time() - t0:.0f}s",
        flush=True,
    )
    res = {"n_samples": len(samples), "verify_max_diff": err, "variants": {}}
    brng = np.random.default_rng(12345)
    for var in VARIANTS:
        per_seed = []
        for s in range(N_SEEDS):
            items, nempty = build(prepped, var, SEED0 + s)
            p, n = pooled(items, "pd", "nd")
            pp, np_ = pooled(items, "pp", "np_")
            per_seed.append(
                dict(
                    auc_depth=auc_fast(p, n),
                    auc_pit=auc_fast(pp, np_),
                    n=len(items),
                    nempty=nempty,
                    bg_pit_share=float(np.mean(np_ > 0)) if len(np_) else None,
                    bg_pit20_share=float(np.mean(np_ >= PIT_MIN)) if len(np_) else None,
                    pond_cells_pit_share=float(np.mean(pp > 0)) if len(pp) else None,
                    pond_cells_pit20_share=float(np.mean(pp >= PIT_MIN)) if len(pp) else None,
                )
            )
            if s == 0:
                items0, nempty0 = items, nempty
                ci_d = boot(items, "pd", "nd", brng, "pond")
                ci_dg = boot(items, "pd", "nd", brng, "grid")
                ci_p = boot(items, "pp", "np_", brng, "pond")
                small = [i for i in items if i["ncell"] < 100]
                ci_small = boot(small, "pd", "nd", brng, "pond") if len(small) >= 10 else None
                auc_small = auc_fast(*pooled(small, "pd", "nd")) if small else None
        a = [x["auc_depth"] for x in per_seed]
        r = dict(
            desc=VARIANTS[var],
            n_ponds=per_seed[0]["n"],
            n_ponds_without_bg=nempty0,
            auc_depth=per_seed[0]["auc_depth"],
            ci_depth_pond=ci_d,
            ci_depth_grid=ci_dg,
            auc_depth_seeds_mean=float(np.mean(a)),
            auc_depth_seeds_min=float(np.min(a)),
            auc_depth_seeds_max=float(np.max(a)),
            auc_pit=per_seed[0]["auc_pit"],
            ci_pit_pond=ci_p,
            auc_pit_seeds_min=float(np.min([x["auc_pit"] for x in per_seed])),
            auc_pit_seeds_max=float(np.max([x["auc_pit"] for x in per_seed])),
            share_ponds_with_pit=float(np.mean([i["has_pit"] for i in items0])),
            share_ponds_with_pit20=float(np.mean([i["has_pit20"] for i in items0])),
            mean_pit_share_of_pond_cells=float(np.mean([i["pit_share_all"] for i in items0])),
            pit_share_pond_drawn=per_seed[0]["pond_cells_pit_share"],
            pit20_share_pond_drawn=per_seed[0]["pond_cells_pit20_share"],
            bg_pit_share=per_seed[0]["bg_pit_share"],
            bg_pit20_share=per_seed[0]["bg_pit20_share"],
            small_ponds_n=len(small),
            small_ponds_auc=auc_small,
            small_ponds_ci=ci_small,
        )
        res["variants"][var] = r
        print(var, json.dumps(r, ensure_ascii=False), f"{time.time() - t0:.0f}s", flush=True)
        (W / "honest_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
