#!/usr/bin/env bash
# Build a pandoc-compatible reference .pptx that carries Apart's branding.
#
# Why this exists: pandoc's `--reference-doc` matches slide layouts by exact
# PowerPoint names ("Title and Content", "Section Header", ...) AND expects
# specific placeholder types. A raw Google-Slides export uses different layout
# names (TITLE_AND_BODY, ...) and incompatible placeholders, so pandoc falls
# back to its own defaults and the branding is lost.
#
# Strategy: take pandoc's OWN default reference (guaranteed-correct structure)
# as the skeleton, then graft Apart's *look* onto it:
#   - theme1.xml         -> colors + fonts
#   - master background  -> dark fill
#   - master logo(s)     -> the picture(s) on Apart's master
#   - slide dimensions   -> Apart's sldSz
# All of these are extracted dynamically from the Apart export, so updating to a
# new brand template is just: re-export from Google Slides, drop it in, re-run.
#
# Usage:
#   ./build-apart-reference.sh [path-to-apart-export.pptx]
# With no argument it uses the committed `source-template.pptx` next to this
# script, so a plain re-run reproduces the reference and editing the DS_* tokens
# above then re-running applies them. Pass an explicit path only when adopting a
# NEW Apart template; then replace source-template.pptx with it and commit both.
# Output: ./apart-reference.pptx (next to this script)

set -euo pipefail

# Associative arrays below need Bash 4+ (macOS ships /bin/bash 3.2).
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  echo "ERROR: needs Bash 4+ (found ${BASH_VERSION:-unknown}). Try Homebrew bash." >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${1:-$HERE/source-template.pptx}"
OUT="$HERE/apart-reference.pptx"

# --- Apart Design System tokens (authoritative; edit here on a rebrand) -------
# Source of truth: Branding Notion / "Apart Design System" kit. When ALIGN=1
# (default) these OVERRIDE whatever the exported template carries, so the
# reference stays on-brand even if the Google Slides template drifts. Set
# ALIGN=0 to instead mirror the export verbatim (Arial / its own colors).
ALIGN="${ALIGN:-1}"
DS_FONT="Inter"          # decks use Inter; Neuemontreal is web/logo-only (paid)
DS_BG_DARK="101010"      # dark slide background (live homepage, verified)
DS_TEXT="F7F7F5"         # off-white text on dark (live homepage, verified)
DS_GREEN="46FF99"        # brand green — live homepage CSS + favicon (#44ff98 ~ #46ff99)
DS_GREEN_FILL="26C26B"   # darker green for visited links / fills
# Corner logo: the official transparent vector asterisk, pre-rendered crisp,
# recolored to the live brand green. Re-render from the SVG with:
#   rsvg-convert -w 1024 -h 1024 assets/apart_asterisk_green.svg -o assets/apart_asterisk_green.png
DS_LOGO="$HERE/assets/apart_asterisk_green.png"
DS_LOGO_SIZE="548640"        # logo square size in EMU (548640 = 0.6 in)
DS_LOGO_MARGIN_SIDE="152400" # gap from the right edge in EMU (0.167 in)
DS_LOGO_MARGIN_BOTTOM="249375" # gap from bottom edge in EMU (0.27 in)
# Type scale: Apart titles are left-aligned, bold, large, with tight display
# tracking; body gets a touch more line spacing than pandoc's default.
DS_TITLE_SIZE="4000"        # content-slide title size in 1/100 pt (4000 = 40 pt)
DS_COVER_TITLE_SIZE="5400"  # cover (title slide) title size in 1/100 pt (5400 = 54 pt)
DS_TITLE_SPC="-60"          # title letter tracking in 1/100 pt (~ -0.02em)
DS_BODY_SIZE="2000"         # top-level body text in 1/100 pt (2000 = 20 pt; pandoc default 24)
DS_BODY_SIZE_L2="1800"      # nested-bullet body text in 1/100 pt (1800 = 18 pt; pandoc default 21)
DS_BODY_LNSPC="128000"      # body line spacing as 1/1000 percent (128000 = 128%)
DS_BODY_SPCBEF="55000"      # space before each body paragraph, 1/1000 % of line (55%)
DS_TABLE_RULE="2A2A2A"      # subtle hex grey for table row rules (Apart dark hairline)
# -----------------------------------------------------------------------------

[ -f "$SRC" ] || { echo "ERROR: source template not found: $SRC" >&2; exit 1; }
for dep in pandoc unzip zip perl; do
  command -v "$dep" >/dev/null || { echo "ERROR: '$dep' not on PATH" >&2; exit 1; }
done
# Validate numeric tokens (EMU positions/sizes and pt values) up front.
for v in DS_LOGO_SIZE DS_LOGO_MARGIN_SIDE DS_LOGO_MARGIN_BOTTOM DS_TITLE_SIZE DS_COVER_TITLE_SIZE DS_BODY_SIZE DS_BODY_SIZE_L2 DS_BODY_LNSPC DS_BODY_SPCBEF; do
  [[ "${!v}" =~ ^[0-9]+$ ]] || { echo "ERROR: $v must be a non-negative integer (got '${!v}')" >&2; exit 1; }
done
[[ "$DS_TITLE_SPC" =~ ^-?[0-9]+$ ]] || { echo "ERROR: DS_TITLE_SPC must be an integer (got '$DS_TITLE_SPC')" >&2; exit 1; }

echo "Source template : $SRC"
echo "Output          : $OUT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
BASE="$WORK/base"   # pandoc skeleton (gets modified in place)
AP="$WORK/apart"
mkdir -p "$BASE" "$AP"

# 1. Fresh pandoc skeleton (tracks the installed pandoc version)
pandoc --print-default-data-file reference.pptx > "$WORK/pandoc-default.pptx"
unzip -q "$WORK/pandoc-default.pptx" -d "$BASE"

# 2. Unpack the Apart export
unzip -q "$SRC" -d "$AP"

MASTER="$BASE/ppt/slideMasters/slideMaster1.xml"
MASTER_RELS="$BASE/ppt/slideMasters/_rels/slideMaster1.xml.rels"
AP_MASTER="$AP/ppt/slideMasters/slideMaster1.xml"
AP_MASTER_RELS="$AP/ppt/slideMasters/_rels/slideMaster1.xml.rels"

# 3. Theme (colors + fonts)
cp "$AP/ppt/theme/theme1.xml" "$BASE/ppt/theme/theme1.xml"
echo "  + grafted theme1.xml (colors + fonts)"

# 4. Slide dimensions: copy Apart's <p:sldSz .../> into the skeleton
AP_SLDSZ="$(perl -0777 -ne 'print $1 if /(<p:sldSz[^>]*\/>)/' "$AP/ppt/presentation.xml")"
if [ -n "$AP_SLDSZ" ]; then
  export AP_SLDSZ
  perl -0777 -i -pe 's{<p:sldSz[^>]*/>}{$ENV{AP_SLDSZ}}' "$BASE/ppt/presentation.xml"
  echo "  + set slide size: $AP_SLDSZ"
fi

# 5. Master background: replace the skeleton's <p:bg>...</p:bg> with Apart's
AP_BG="$(perl -0777 -ne 'print $1 if /(<p:bg>.*?<\/p:bg>)/s' "$AP_MASTER")"
if [ -n "$AP_BG" ]; then
  AP_BG="$AP_BG" perl -0777 -i -pe 's{<p:bg>.*?</p:bg>}{$ENV{AP_BG}}s' "$MASTER"
  echo "  + grafted master background"
fi

# 6. Logo(s): copy media, add relationships, inject <p:pic> blocks into the master.
#    Generalised over however many images sit on Apart's master.
mkdir -p "$BASE/ppt/media"
# Map: Apart rId -> media basename (only image relationships)
declare -A AP_IMG
while IFS= read -r line; do
  rid="$(printf '%s' "$line" | perl -ne 'print $1 if /Id="([^"]+)"/')"
  tgt="$(printf '%s' "$line" | perl -ne 'print $1 if /Target="\.\.\/media\/([^"]+)"/')"
  [ -n "$rid" ] && [ -n "$tgt" ] && AP_IMG["$rid"]="$tgt"
done < <(grep -oE '<Relationship[^>]*relationships/image[^>]*>' "$AP_MASTER_RELS")

if [ ${#AP_IMG[@]} -gt 0 ]; then
  # Extract pic blocks from Apart master, remap each r:embed to a fresh rId.
  PICS=""
  RELS_ADD=""
  i=900   # rId/shape-id base well clear of pandoc's skeleton (rId1..rId12)
  for rid in "${!AP_IMG[@]}"; do
    img="${AP_IMG[$rid]}"
    src="$AP/ppt/media/$img"
    # In alignment mode, swap the export's low-res raster for the bundled
    # high-res transparent asterisk (only when the master carries a single image).
    if [ "$ALIGN" = "1" ] && [ -f "$DS_LOGO" ] && [ ${#AP_IMG[@]} -eq 1 ]; then
      src="$DS_LOGO"; LOGO_SWAPPED=1
      img="${img%.*}.${DS_LOGO##*.}"   # match media extension to the swapped asset
    fi
    cp "$src" "$BASE/ppt/media/$img"
    newrid="rId$i"
    RELS_ADD="$RELS_ADD<Relationship Id=\"$newrid\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image\" Target=\"../media/$img\"/>"
    picid=$(( 9000 + i ))   # unique shape id, can't collide with skeleton master
    i=$((i+1))
    # pull every <p:pic> whose blip embeds this rid, rewrite the embed
    block="$(AP_RID="$rid" perl -0777 -ne '
      while (/(<p:pic>.*?<\/p:pic>)/sg) { my $p=$1; print $p if $p =~ /r:embed="\Q$ENV{AP_RID}\E"/ }
    ' "$AP_MASTER")"
    block="$(printf '%s' "$block" | perl -pe "s/r:embed=\"\\Q$rid\\E\"/r:embed=\"$newrid\"/g")"
    [ -n "$block" ] || { echo "ERROR: no <p:pic> found for image $img on the export master" >&2; exit 1; }
    # Renumber the inserted picture's shape id (export ids start low and would
    # otherwise collide with pandoc's master shapes).
    block="$(printf '%s' "$block" | perl -pe "s/(<p:cNvPr )id=\"\\d+\"/\${1}id=\"$picid\"/")"
    # When we swapped in the bundled asterisk, also resize and anchor it in the
    # bottom-right corner (the export's placement is too small, and bottom-right
    # stays clear of left-aligned body text). Position derived from slide size.
    if [ "${LOGO_SWAPPED:-0}" = "1" ]; then
      SLIDE_CY="$(printf '%s' "$AP_SLDSZ" | perl -ne 'print $1 if /cy="(\d+)"/')"
      SLIDE_CX="$(printf '%s' "$AP_SLDSZ" | perl -ne 'print $1 if /cx="(\d+)"/')"
      [[ "$SLIDE_CY" =~ ^[0-9]+$ && "$SLIDE_CX" =~ ^[0-9]+$ ]] || { echo "ERROR: could not parse slide size from '$AP_SLDSZ'" >&2; exit 1; }
      LX=$(( SLIDE_CX - DS_LOGO_MARGIN_SIDE - DS_LOGO_SIZE ))
      LY=$(( SLIDE_CY - DS_LOGO_MARGIN_BOTTOM - DS_LOGO_SIZE ))
      { [ "$LX" -ge 0 ] && [ "$LY" -ge 0 ]; } || { echo "ERROR: logo would sit off-slide (x=$LX y=$LY); check DS_LOGO_SIZE/margins" >&2; exit 1; }
      block="$(printf '%s' "$block" | perl -pe "s{<a:off [^/]*/>}{<a:off x=\"$LX\" y=\"$LY\"/>}; s{<a:ext [^/]*/>}{<a:ext cx=\"$DS_LOGO_SIZE\" cy=\"$DS_LOGO_SIZE\"/>}")"
    fi
    PICS="$PICS$block"
  done
  # Inject pics just before </p:spTree> on the master
  PICS="$PICS" perl -0777 -i -pe 's{</p:spTree>}{$ENV{PICS}</p:spTree>}' "$MASTER"
  # Add the image relationships to the master rels
  RELS_ADD="$RELS_ADD" perl -0777 -i -pe 's{</Relationships>}{$ENV{RELS_ADD}</Relationships>}' "$MASTER_RELS"
  # Declare a content-type default for each media extension actually present.
  for ext in $(/bin/ls "$BASE/ppt/media" | sed 's/.*\.//' | tr '[:upper:]' '[:lower:]' | sort -u); do
    case "$ext" in
      png) ct="image/png" ;; jpg|jpeg) ct="image/jpeg" ;; gif) ct="image/gif" ;;
      svg) ct="image/svg+xml" ;; emf) ct="image/x-emf" ;; wmf) ct="image/x-wmf" ;;
      *) ct="" ;;
    esac
    [ -z "$ct" ] && continue
    grep -q "Extension=\"$ext\"" "$BASE/[Content_Types].xml" && continue
    EXT="$ext" CT="$ct" perl -0777 -i -pe 's{(<Types[^>]*>)}{$1<Default Extension="$ENV{EXT}" ContentType="$ENV{CT}"/>}' "$BASE/[Content_Types].xml"
  done
  if [ "${LOGO_SWAPPED:-0}" = "1" ]; then
    echo "  + added master logo (swapped in bundled high-res transparent asterisk)"
  else
    echo "  + added ${#AP_IMG[@]} logo image(s) to master (from export)"
  fi
fi

# 6b. Apply Apart Design System tokens (override the export's theme/bg/fonts).
if [ "$ALIGN" = "1" ]; then
  THEME="$BASE/ppt/theme/theme1.xml"
  # Fonts: Inter for both major (display) and minor (body) Latin faces.
  DS_FONT="$DS_FONT" perl -0777 -i -pe 's{(<a:majorFont>.*?<a:latin typeface=")[^"]*}{$1$ENV{DS_FONT}}s' "$THEME"
  DS_FONT="$DS_FONT" perl -0777 -i -pe 's{(<a:minorFont>.*?<a:latin typeface=")[^"]*}{$1$ENV{DS_FONT}}s' "$THEME"
  # Color slots (clrMap: tx1=dk1, bg1=lt1). Scope each replace to its element.
  DS_TEXT="$DS_TEXT"           perl -0777 -i -pe 's{(<a:dk1>\s*<a:srgbClr val=")[0-9A-Fa-f]{6}}{$1$ENV{DS_TEXT}}s'        "$THEME"
  DS_BG_DARK="$DS_BG_DARK"     perl -0777 -i -pe 's{(<a:lt1>\s*<a:srgbClr val=")[0-9A-Fa-f]{6}}{$1$ENV{DS_BG_DARK}}s'     "$THEME"
  DS_GREEN="$DS_GREEN"         perl -0777 -i -pe 's{(<a:accent1>\s*<a:srgbClr val=")[0-9A-Fa-f]{6}}{$1$ENV{DS_GREEN}}s'   "$THEME"
  DS_GREEN_FILL="$DS_GREEN_FILL" perl -0777 -i -pe 's{(<a:accent3>\s*<a:srgbClr val=")[0-9A-Fa-f]{6}}{$1$ENV{DS_GREEN_FILL}}s' "$THEME"
  DS_GREEN="$DS_GREEN"         perl -0777 -i -pe 's{(<a:hlink>\s*<a:srgbClr val=")[0-9A-Fa-f]{6}}{$1$ENV{DS_GREEN}}s'     "$THEME"
  DS_GREEN_FILL="$DS_GREEN_FILL" perl -0777 -i -pe 's{(<a:folHlink>\s*<a:srgbClr val=")[0-9A-Fa-f]{6}}{$1$ENV{DS_GREEN_FILL}}s' "$THEME"
  # Master background: force a flat DS-dark solid fill, template-independent.
  DS_BG_DARK="$DS_BG_DARK" perl -0777 -i -pe 's{<p:bg>.*?</p:bg>}{<p:bg><p:bgPr><a:solidFill><a:srgbClr val="$ENV{DS_BG_DARK}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>}s' "$MASTER"
  echo "  + applied Apart Design System tokens (Inter, #$DS_BG_DARK bg, #$DS_TEXT text, #$DS_GREEN green)"

  # 6c. Type scale + layout polish on the master text styles.
  export DS_TITLE_SIZE DS_COVER_TITLE_SIZE DS_TITLE_SPC DS_BODY_SIZE DS_BODY_SIZE_L2 DS_BODY_LNSPC DS_BODY_SPCBEF
  # Content-slide titles: left-align, bold, larger, tight display tracking.
  # Each edit strips any prior value first so it stays idempotent if pandoc's
  # default already carries the attribute (no duplicate attrs / elements).
  perl -0777 -i -pe 's{(<p:titleStyle>.*?</p:titleStyle>)}{
    my $b=$1;
    $b =~ s/algn="ctr"/algn="l"/g;
    $b =~ s/(<a:defRPr\b[^>]*?)\s+b="[^"]*"/$1/g;
    $b =~ s/(<a:defRPr\b[^>]*?)\s+spc="[^"]*"/$1/g;
    $b =~ s/(<a:defRPr sz=")\d+(")/$1.$ENV{DS_TITLE_SIZE}.$2/e;
    $b =~ s/(<a:defRPr\b[^>]*?)(>)/$1 . " b=\"1\" spc=\"$ENV{DS_TITLE_SPC}\"" . $2/e;
    $b;
  }se' "$MASTER"
  # Body: larger text plus more line spacing + space between paragraphs than
  # pandoc's default, so title/body and bullets breathe (lvl1 + lvl2). Each edit
  # is idempotent.
  perl -0777 -i -pe 's{(<p:bodyStyle>.*?</p:bodyStyle>)}{
    my $b=$1;
    my %sz = (1 => $ENV{DS_BODY_SIZE}, 2 => $ENV{DS_BODY_SIZE_L2});
    for my $lvl (1,2) {
      $b =~ s{(<a:lvl${lvl}pPr\b[^>]*>)\s*<a:lnSpc>.*?</a:lnSpc>}{$1}s;
      $b =~ s{(<a:lvl${lvl}pPr\b[^>]*>)}{$1<a:lnSpc><a:spcPct val="$ENV{DS_BODY_LNSPC}"/></a:lnSpc>};
      $b =~ s{(<a:lvl${lvl}pPr\b[^>]*><a:lnSpc>.*?</a:lnSpc>)\s*<a:spcBef>.*?</a:spcBef>}{$1}s;
      $b =~ s{(<a:lvl${lvl}pPr\b[^>]*><a:lnSpc>.*?</a:lnSpc>)}{$1<a:spcBef><a:spcPct val="$ENV{DS_BODY_SPCBEF}"/></a:spcBef>}s;
      $b =~ s{(<a:lvl${lvl}pPr\b.*?<a:defRPr sz=")\d+(")}{$1$sz{$lvl}$2}s;
    }
    $b;
  }se' "$MASTER"
  # (The date footer keeps the master's default bottom-left placement; the logo
  # sits bottom-right.)

  # 6d. Title slide (cover): left-align + enlarge the cover title; left-align
  # the subtitle block. The cover title gets its own bigger size so it reads as
  # a hero.
  LAYOUT1="$BASE/ppt/slideLayouts/slideLayout1.xml"
  if [ -f "$LAYOUT1" ]; then
    DS_COVER_TITLE_SIZE="$DS_COVER_TITLE_SIZE" perl -0777 -i -pe 's{(<p:sp>.*?</p:sp>)}{
      my $s=$1;
      $s =~ s{<a:lstStyle/>}{<a:lstStyle><a:lvl1pPr algn="l"><a:defRPr sz="$ENV{DS_COVER_TITLE_SIZE}" b="1"/></a:lvl1pPr></a:lstStyle>} if $s =~ /type="ctrTitle"/;
      $s =~ s/algn="ctr"/algn="l"/g if $s =~ /type="subTitle"/;
      $s;
    }gse' "$LAYOUT1"
  fi
  echo "  + applied type scale (cover ${DS_COVER_TITLE_SIZE%??}pt / title ${DS_TITLE_SIZE%??}pt bold), body spacing, left cover"

  # 6e. Brand table style. pandoc emits tables referencing the fixed GUID below
  # but ships an EMPTY tableStyles.xml — so cells get the renderer's default
  # (black text, no borders), invisible on the dark background. Define the GUID:
  # light cell text, subtle grey row rules, a green rule under the header row,
  # no fills. pandoc preserves a populated tableStyles.xml from the reference.
  TBL_GUID="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"
  cat > "$BASE/ppt/tableStyles.xml" <<XML
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="$TBL_GUID"><a:tblStyle styleId="$TBL_GUID" styleName="Apart Dark"><a:wholeTbl><a:tcTxStyle><a:fontRef idx="minor"/><a:schemeClr val="tx1"/></a:tcTxStyle><a:tcStyle><a:tcBdr><a:bottom><a:ln w="6350" cap="flat"><a:solidFill><a:srgbClr val="$DS_TABLE_RULE"/></a:solidFill></a:ln></a:bottom></a:tcBdr><a:fill><a:noFill/></a:fill></a:tcStyle></a:wholeTbl><a:firstRow><a:tcTxStyle b="on"><a:fontRef idx="minor"/><a:schemeClr val="tx1"/></a:tcTxStyle><a:tcStyle><a:tcBdr><a:bottom><a:ln w="19050" cap="flat"><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:ln></a:bottom></a:tcBdr><a:fill><a:noFill/></a:fill></a:tcStyle></a:firstRow></a:tblStyle></a:tblStyleLst>
XML
  # Wire content-type + presentation rel if pandoc's skeleton didn't already.
  grep -q 'tableStyles' "$BASE/[Content_Types].xml" || perl -0777 -i -pe 's{</Types>}{<Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/></Types>}' "$BASE/[Content_Types].xml"
  grep -q 'tableStyles' "$BASE/ppt/_rels/presentation.xml.rels" || perl -0777 -i -pe 's{</Relationships>}{<Relationship Id="rIdTblStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/></Relationships>}' "$BASE/ppt/_rels/presentation.xml.rels"
  echo "  + wrote brand table style (light text, green header rule)"

  # 6f. Content-with-Caption layout (slideLayout8): pandoc routes table / image
  # slides here, but its title is a tiny 15pt box top-left with the content
  # shoved into a right-hand column. Re-lay it as a normal content slide:
  # full-width 40pt title on top (inherit the master title style), the caption
  # line under it, and the content (table) full-width below.
  LAYOUT8="$BASE/ppt/slideLayouts/slideLayout8.xml"
  if [ -f "$LAYOUT8" ]; then
    perl -0777 -i -pe 's{(<p:sp>.*?</p:sp>)}{
      my $s=$1;
      if ($s =~ /<p:ph type="title"/) {
        $s =~ s{<a:off [^/]*/>}{<a:off x="457200" y="205979"/>};
        $s =~ s{<a:ext [^/]*/>}{<a:ext cx="8229600" cy="857250"/>};
        $s =~ s{<a:lstStyle>.*?</a:lstStyle>}{<a:lstStyle/>}s;
      } elsif ($s =~ /<p:ph type="body"[^>]*idx="2"/) {
        $s =~ s{<a:off [^/]*/>}{<a:off x="457200" y="1130000"/>};
        $s =~ s{<a:ext [^/]*/>}{<a:ext cx="8229600" cy="520000"/>};
      } elsif ($s =~ m{<p:ph idx="1"\s*/>}) {
        $s =~ s{<a:off [^/]*/>}{<a:off x="457200" y="1720000"/>};
        $s =~ s{<a:ext [^/]*/>}{<a:ext cx="8229600" cy="2880000"/>};
      }
      $s;
    }gse' "$LAYOUT8"
  fi
  echo "  + re-laid table/caption layout (full-width title + content)"
fi

# 7. Package to a temp file, validate everything, then move into place atomically
# (so a failed build never leaves a broken $OUT behind).
TMPOUT="$WORK/out.pptx"
( cd "$BASE"
  # [Content_Types].xml goes in as the first archive entry. Unlike ODF's
  # mimetype, OOXML does NOT require it stored uncompressed, so normal deflate
  # is fine (PowerPoint/Google Slides/pandoc all read it). The exclude pattern
  # escapes the literal brackets ([[]/[]]) so the recursive add doesn't re-add it.
  zip -q -X "$TMPOUT" '[Content_Types].xml'
  zip -q -rX "$TMPOUT" . -x '[[]Content_Types[]].xml'
)

# 7a. Integrity: must be a valid zip.
unzip -tqq "$TMPOUT" >/dev/null 2>&1 || { echo "ERROR: output is not a valid zip archive" >&2; exit 1; }

# 7b. Verify the brand edits actually landed (catches a silent no-op if pandoc's
# default reference structure ever changes under us).
assert_in() {  # member  fixed-pattern  message
  # Process substitution (not a pipe) so an early grep match can't SIGPIPE unzip
  # into a false failure under `set -o pipefail`.
  grep -qF -- "$2" < <(unzip -p "$TMPOUT" "$1") || { echo "ERROR: $3 (expected '$2' in $1)" >&2; exit 1; }
}
assert_member() { grep -q -- "$1" < <(unzip -l "$TMPOUT") || { echo "ERROR: missing $1" >&2; exit 1; }; }
assert_member ppt/slideMasters/slideMaster1.xml
if [ "$ALIGN" = "1" ]; then
  assert_in ppt/theme/theme1.xml "typeface=\"$DS_FONT\""                "font not applied"
  assert_in ppt/slideMasters/slideMaster1.xml "srgbClr val=\"$DS_BG_DARK\"" "dark background not applied"
  assert_in ppt/slideMasters/slideMaster1.xml 'b="1" spc='               "title type scale not applied"
  assert_in ppt/slideMasters/slideMaster1.xml "spcPct val=\"$DS_BODY_LNSPC\"" "body line spacing not applied"
  assert_in ppt/slideMasters/slideMaster1.xml "spcPct val=\"$DS_BODY_SPCBEF\"" "body space-before not applied"
  assert_in ppt/slideMasters/slideMaster1.xml "<a:defRPr sz=\"$DS_BODY_SIZE\"" "body text size not applied"
  assert_in ppt/slideMasters/slideMaster1.xml '<p:pic>'                 "logo not injected on master"
  assert_in ppt/slideLayouts/slideLayout1.xml "sz=\"$DS_COVER_TITLE_SIZE\"" "cover title size not applied"
  assert_in ppt/tableStyles.xml 'styleName="Apart Dark"'                "brand table style not written"
  assert_in ppt/slideLayouts/slideLayout8.xml 'y="205979"'              "table/caption layout not re-laid"
fi

# 7c. Smoke-compile: pandoc must accept it WITH NO missing-layout fallback.
TMPMD="$WORK/smoke.md"
cat > "$TMPMD" <<'MD'
---
title: Reference Smoke Test
subtitle: Apart branding check
---

## Section divider

# A section

## Title and bullets

Body line.

- one
- two

## Two ideas side by side

::: {.columns}
::: {.column}
Left column.
:::
::: {.column}
Right column.
:::
:::
MD
if ! pandoc -t pptx --slide-level=2 --reference-doc="$TMPOUT" "$TMPMD" -o "$WORK/smoke.pptx" 2>"$WORK/warn.txt"; then
  echo "ERROR: pandoc failed to compile against the reference:" >&2; cat "$WORK/warn.txt" >&2; exit 1
fi
if grep -q 'Couldn.t find layout' "$WORK/warn.txt"; then
  echo "ERROR: pandoc fell back to default layouts (layout names not matched):" >&2; cat "$WORK/warn.txt" >&2; exit 1
fi

# 7d. All checks passed — publish.
mv "$TMPOUT" "$OUT"
echo "Done -> $OUT"
echo "OK: valid package, brand edits verified, pandoc compiles with no fallbacks."
