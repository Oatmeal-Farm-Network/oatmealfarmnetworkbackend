from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db
import os
import time, re
from app.routers.translation import translate_fields, translate_list

router = APIRouter(prefix="/api/livestock", tags=["livestock"])

# Breed/species encyclopedia images live in the prod Animals/ library.
# Keep this separate from GCS_IMAGES_BUCKET (staging uploads) so staging can
# still write to oatmeal-farm-network-images-staging without breaking reads.
GCS_LIVESTOCK_IMAGES_BUCKET = os.getenv(
    "GCS_LIVESTOCK_IMAGES_BUCKET",
    "oatmeal-farm-network-images",
)
GCS_IMAGES_URL = f"https://storage.googleapis.com/{GCS_LIVESTOCK_IMAGES_BUCKET}/Animals"

OLD_DOMAINS = [
    'oatmealfarmnetwork.com', 'livestockofamerica.com',
    'livestockoftheworld.com', 'alpacainfinity.com',
    'globallivestocksolutions.com',
]

def _safe_text(value) -> str | None:
    """Coerce DB text (str/bytes/legacy TEXT) to a JSON-safe string."""
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    else:
        value = str(value)
    value = value.replace("\x00", "")
    # Drop lone surrogates that break JSON on Cloud Run (pytds).
    return value.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")


def _fix_image_url(url: str | None) -> str | None:
    if not url:
        return None
    url = _safe_text(url)
    if not url:
        return None
    url = url.strip()
    if len(url) < 4:
        return None
    if url.lower().startswith('http'):
        url = re.sub(r'^http:', 'https:', url, flags=re.IGNORECASE)
        for domain in OLD_DOMAINS:
            if domain in url.lower():
                filename = url.split('/')[-1].strip()
                if filename and len(filename) > 3:
                    return f"{GCS_IMAGES_URL}/{filename}"
        return url
    if url.lower().startswith('/uploads/'):
        filename = url[9:].strip()
        if filename and len(filename) > 3:
            return f"{GCS_IMAGES_URL}/{filename}"
        return None
    if '/' not in url and len(url) > 4:
        return f"{GCS_IMAGES_URL}/{url}"
    filename = url.split('/')[-1].strip()
    if filename and len(filename) > 3:
        return f"{GCS_IMAGES_URL}/{filename}"
    return None


def _breed_list_item(row) -> dict | None:
    """Build a breed list card; skip rows that cannot be serialized."""
    try:
        breed_id = row.BreedLookupID
        if breed_id is None:
            return None
        return {
            "breed_id": int(breed_id),
            "breed": (_safe_text(row.Breed) or "").strip(),
            "description": _safe_text(row.Breeddescription),
            "image": _fix_image_url(row.BreedImage),
            "image_caption": _safe_text(row.BreedImageCaption),
        }
    except Exception:
        import logging
        logging.exception(
            "Skipping corrupt breed row BreedLookupID=%s",
            getattr(row, "BreedLookupID", None),
        )
        return None

SLUG_TO_SPECIES_ID = {
    'alpacas': 2, 'bison': 9, 'buffalo': 34, 'camels': 18, 'cattle': 8,
    'chickens': 13, 'crocodiles': 25, 'dogs': 3, 'deer': 21, 'donkeys': 7, 'ducks': 15,
    'emus': 19, 'geese': 22, 'goats': 6, 'guinea-fowl': 26, 'honey-bees': 23,
    'horses': 5, 'llamas': 4, 'musk-ox': 27, 'ostriches': 28, 'pheasants': 29,
    'pigs': 12, 'pigeons': 30, 'quails': 31, 'rabbits': 11, 'sheep': 10,
    'snails': 33, 'turkeys': 14, 'yaks': 17,
}

SLUG_TO_LABEL = {
    'alpacas': 'Alpacas', 'bison': 'Bison', 'buffalo': 'Buffalo', 'camels': 'Camels',
    'cattle': 'Cattle', 'chickens': 'Chickens', 'crocodiles': 'Crocodiles & Alligators',
    'deer': 'Deer', 'dogs': 'Working Dogs', 'donkeys': 'Donkeys', 'ducks': 'Ducks', 'emus': 'Emus',
    'geese': 'Geese', 'goats': 'Goats', 'guinea-fowl': 'Guinea Fowl',
    'honey-bees': 'Honey Bees', 'horses': 'Horses', 'llamas': 'Llamas',
    'musk-ox': 'Musk Ox', 'ostriches': 'Ostriches', 'pheasants': 'Pheasants',
    'pigs': 'Pigs', 'pigeons': 'Pigeons', 'quails': 'Quails', 'rabbits': 'Rabbits',
    'sheep': 'Sheep', 'snails': 'Snails', 'turkeys': 'Turkeys', 'yaks': 'Yaks',
}

# Simple in-memory cache
_cache = {}
CACHE_TTL = 300  # 5 minutes

def cache_get(key):
    entry = _cache.get(key)
    if entry and time.time() - entry['t'] < CACHE_TTL:
        return entry['v']
    return None

def cache_set(key, value):
    _cache[key] = {'v': value, 't': time.time()}


@router.get("/counts")
def get_counts(db: Session = Depends(get_db)):
    cached = cache_get('counts')
    if cached:
        return cached
    try:
        rows = db.execute(
            text("SELECT SpeciesID, COUNT(*) AS BreedCount FROM SpeciesBreedLookupTable GROUP BY SpeciesID")
        ).fetchall()
        id_to_count = {r.SpeciesID: r.BreedCount for r in rows}
        counts = {}
        total = 0
        for slug, sid in SLUG_TO_SPECIES_ID.items():
            val = id_to_count.get(sid, 0)
            counts[slug] = val
            total += val
        result = {"counts": counts, "total": total}
        cache_set('counts', result)
        return result
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/species/{slug}/letters")
def get_species_letters(slug: str, db: Session = Depends(get_db)):
    """Returns species info + list of available first letters for breeds."""
    cache_key = f'letters_{slug}'
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        species_id = SLUG_TO_SPECIES_ID.get(slug)
        if not species_id:
            raise HTTPException(status_code=404, detail="Species not found")

        info_row = db.execute(
            text("SELECT SingularTerm, PluralTerm, SpeciesText1, SpeciesImage1 FROM SpeciesAvailable WHERE SpeciesID = :sid"),
            {"sid": species_id}
        ).fetchone()

        species_info = None
        if info_row:
            species_info = {
                "singular": _safe_text(info_row.SingularTerm),
                "plural": _safe_text(info_row.PluralTerm),
                "description": _safe_text(info_row.SpeciesText1),
                "main_image": _fix_image_url(info_row.SpeciesImage1),
            }

        # Get distinct first letters (only A–Z with at least one breed name)
        rows = db.execute(
            text("""
               SELECT DISTINCT UPPER(LEFT(LTRIM(Breed), 1)) AS FirstLetter
               FROM SpeciesBreedLookupTable
               WHERE SpeciesID = :sid
                 AND Breed IS NOT NULL
                 AND LTRIM(RTRIM(Breed)) <> ''
                 AND UPPER(LEFT(LTRIM(Breed), 1)) LIKE '[A-Z]'
               ORDER BY FirstLetter
            """),
            {"sid": species_id}
        ).fetchall()

        letters = [_safe_text(r.FirstLetter) for r in rows if r.FirstLetter]
        letters = [L for L in letters if L]

        # Total breed count so frontend can decide whether to paginate
        total_row = db.execute(
            text("""
                SELECT COUNT(*) AS cnt FROM SpeciesBreedLookupTable
                WHERE SpeciesID = :sid AND Breed IS NOT NULL AND Breed != ''
            """),
            {"sid": species_id}
        ).fetchone()
        total_breeds = total_row.cnt if total_row else 0

        result = {"species_info": species_info, "letters": letters, "total_breeds": total_breeds}
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/species/{slug}")
def get_species(slug: str, letter: str = None, lang: str = "en", db: Session = Depends(get_db)):
    """Returns breeds for a species, optionally filtered by first letter."""
    if letter and letter.lower() == "all":
        letter = None
    cache_key = f'species_{slug}_{letter or "all"}'
    cached = cache_get(cache_key)
    if cached:
        result = dict(cached)
        result["breeds"] = translate_list(result["breeds"], ["description"], lang, db)
        if result.get("species_info"):
            result["species_info"] = translate_fields(result["species_info"], ["description"], lang, db)
        return result
    try:
        species_id = SLUG_TO_SPECIES_ID.get(slug)
        if not species_id:
            raise HTTPException(status_code=404, detail="Species not found")

        info_row = db.execute(
            text("SELECT SingularTerm, PluralTerm, SpeciesText1, SpeciesImage1 FROM SpeciesAvailable WHERE SpeciesID = :sid"),
            {"sid": species_id}
        ).fetchone()

        species_info = None
        if info_row:
            species_info = {
                "singular": _safe_text(info_row.SingularTerm),
                "plural": _safe_text(info_row.PluralTerm),
                "description": _safe_text(info_row.SpeciesText1),
                "main_image": _fix_image_url(info_row.SpeciesImage1),
            }

        # CONVERT avoids rare legacy TEXT/NTEXT driver decode failures (pytds)
        # that 500 entire species pages (chickens / horses / llamas).
        if letter:
            sql = text("""
               SELECT BreedLookupID,
                      Breed,
                      CONVERT(NVARCHAR(MAX), Breeddescription) AS Breeddescription,
                      CONVERT(NVARCHAR(MAX), BreedImage) AS BreedImage,
                      CONVERT(NVARCHAR(MAX), BreedImageCaption) AS BreedImageCaption
                FROM SpeciesBreedLookupTable
                WHERE SpeciesID = :sid
                AND UPPER(LEFT(LTRIM(Breed), 1)) = :letter
                AND UPPER(LEFT(LTRIM(Breed), 1)) LIKE '[A-Z]'
                ORDER BY Breed
            """)
            params = {"sid": species_id, "letter": letter.upper()}
        else:
            sql = text("""
                SELECT BreedLookupID,
                       Breed,
                       CONVERT(NVARCHAR(MAX), Breeddescription) AS Breeddescription,
                       CONVERT(NVARCHAR(MAX), BreedImage) AS BreedImage,
                       CONVERT(NVARCHAR(MAX), BreedImageCaption) AS BreedImageCaption
                FROM SpeciesBreedLookupTable
                WHERE SpeciesID = :sid
                ORDER BY Breed
            """)
            params = {"sid": species_id}

        try:
            rows = db.execute(sql, params).fetchall()
        except Exception:
            import logging
            logging.exception(
                "Breed detail columns failed for species=%s letter=%s; returning names only",
                slug,
                letter,
            )
            if letter:
                rows = db.execute(
                    text("""
                        SELECT BreedLookupID, Breed,
                               CAST(NULL AS NVARCHAR(MAX)) AS Breeddescription,
                               CAST(NULL AS NVARCHAR(MAX)) AS BreedImage,
                               CAST(NULL AS NVARCHAR(MAX)) AS BreedImageCaption
                        FROM SpeciesBreedLookupTable
                        WHERE SpeciesID = :sid
                        AND UPPER(LEFT(LTRIM(Breed), 1)) = :letter
                        AND UPPER(LEFT(LTRIM(Breed), 1)) LIKE '[A-Z]'
                        ORDER BY Breed
                    """),
                    params,
                ).fetchall()
            else:
                rows = db.execute(
                    text("""
                        SELECT BreedLookupID, Breed,
                               CAST(NULL AS NVARCHAR(MAX)) AS Breeddescription,
                               CAST(NULL AS NVARCHAR(MAX)) AS BreedImage,
                               CAST(NULL AS NVARCHAR(MAX)) AS BreedImageCaption
                        FROM SpeciesBreedLookupTable
                        WHERE SpeciesID = :sid
                        ORDER BY Breed
                    """),
                    params,
                ).fetchall()

        breeds = []
        for r in rows:
            item = _breed_list_item(r)
            if item is not None:
                breeds.append(item)

        result = {
            "species_info": species_info,
            "breeds": breeds,
        }
        cache_set(cache_key, result)
        result = dict(result)
        result["breeds"] = translate_list(result["breeds"], ["description"], lang, db)
        if result.get("species_info"):
            result["species_info"] = translate_fields(result["species_info"], ["description"], lang, db)
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/breed/{breed_id}")
def get_breed(breed_id: int, lang: str = "en", db: Session = Depends(get_db)):
    cached = cache_get(f'breed_{breed_id}')
    if cached:
        return translate_fields(cached, ["description"], lang, db)
    try:
        sql = text("""
            SELECT BreedLookupID, Breed,
                   CONVERT(NVARCHAR(MAX), Breeddescription) AS Breeddescription,
                   CONVERT(NVARCHAR(MAX), BreedImage) AS BreedImage,
                   CONVERT(NVARCHAR(MAX), BreedImageCaption) AS BreedImageCaption,
                   CONVERT(NVARCHAR(MAX), BreedImageOrientation) AS BreedImageOrientation,
                   CONVERT(NVARCHAR(MAX), Breedvideo) AS Breedvideo
            FROM SpeciesBreedLookupTable
            WHERE BreedLookupID = :bid
        """)
        row = db.execute(sql, {"bid": breed_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Breed not found")

        result = {
            "breed_id": row.BreedLookupID,
            "breed": (_safe_text(row.Breed) or "").strip(),
            "description": _safe_text(row.Breeddescription),
            "image": _fix_image_url(row.BreedImage),
            "image_caption": _safe_text(row.BreedImageCaption),
            "image_orientation": _safe_text(row.BreedImageOrientation),
            "video": _safe_text(row.Breedvideo),
        }
        cache_set(f'breed_{breed_id}', result)
        return translate_fields(result, ["description"], lang, db)
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/species-colors/{species_id}")
def get_species_colors(species_id: int, db: Session = Depends(get_db)):
    cache_key = f'colors_{species_id}'
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        rows = db.execute(
            text("SELECT SpeciesColor FROM SpeciesColorlookupTable WHERE SpeciesID = :sid ORDER BY SpeciesColor"),
            {"sid": species_id}
        ).fetchall()
        result = [r.SpeciesColor for r in rows]
        cache_set(cache_key, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/about/{slug}")
def get_about(slug: str, db: Session = Depends(get_db)):
    cached = cache_get(f'about_{slug}')
    if cached:
        return cached
    try:
        species_id = SLUG_TO_SPECIES_ID.get(slug)
        if not species_id:
            raise HTTPException(status_code=404, detail="Species not found")

        info_row = db.execute(
            text("""
                SELECT SingularTerm, PluralTerm, SpeciesDescription,
                       SpeciesText1, SpeciesImage1, SpeciesText2, SpeciesImage2,
                       SpeciesText3, SpeciesImage3, SpeciesText4, SpeciesImage4,
                       SpeciesText5, SpeciesImage5, SpeciesText6, SpeciesImage6,
                       SpeciesText7, SpeciesImage7, SpeciesText8, SpeciesImage8
                FROM SpeciesAvailable
                WHERE SpeciesID = :sid
            """),
            {"sid": species_id}
        ).fetchone()

        if not info_row:
            raise HTTPException(status_code=404, detail="Species not found")

        color_rows = db.execute(
            text("SELECT SpeciesColor FROM SpeciesColorlookupTable WHERE SpeciesID = :sid ORDER BY SpeciesColor"),
            {"sid": species_id}
        ).fetchall()

        sections = []
        for i in range(2, 9):
            txt = getattr(info_row, f'SpeciesText{i}', None)
            img = getattr(info_row, f'SpeciesImage{i}', None)
            if txt:
                sections.append({
                    "title": "",
                    "content": _safe_text(txt),
                    "image": _fix_image_url(img),
                })

        result = {
            "singular": _safe_text(info_row.SingularTerm),
            "plural": _safe_text(info_row.PluralTerm),
            "about_html": _safe_text(info_row.SpeciesText1) or '',
            "main_image": _fix_image_url(info_row.SpeciesImage1),
            "sections": sections,
            "colors": [_safe_text(r.SpeciesColor) for r in color_rows if r.SpeciesColor],
        }
        cache_set(f'about_{slug}', result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
