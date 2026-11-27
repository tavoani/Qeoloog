# Qeoloog 3.49.6

**Lisa 5 – aluskord** litotulbas saab **Impordi mõõteandmed…** kõrval
oleva nupuga **Exceli näidis…** salvestada kaasasoleva näidisfaili koopia.
Failis on `lõpp_m` veerg, varasemad mõõteradade näited ning näidisrida
kõigi nelja migmatiseerumisastme kohta. Internetiühendust ei ole vaja.

English: Save a copy of the bundled Excel measurement example using the
button next to measurement import in the Annex 5 basement log.

## Eelmise versiooni märkused: 3.49.5

**Lisa 5 – aluskord** litotulba mõõteandmete import toetab nüüd
migmatiseerumise astet sügavusvahemike kaupa. Iga astme viirutus kuvatakse
kivimitulbas ja legendis; kivimi värv säilib. Vahemikud saab salvestada
kohaliku objekti juurde. Vt [veerud ja näidis](docs/LISA5_MEASUREMENTS.md).

English: Annex 5 basement logs now import migmatization grades as depth
intervals and show their hatching in the rock column and legend.

## Eelmise versiooni märkused: 3.49.4

**Kohalikud andmed → Litotulp… → Lisa 5 – aluskord → Impordi mõõteandmed…**
lisab CSV-, TSV- või Exceli failist sondi- ja proovitiheduse, magnetilise
vastuvõtlikkuse ning struktuurielemendid. Rajad on eraldi lülitatavad ja
ilmuvad nii eelvaates kui ka PDF- ja SVG-ekspordis. **Salvesta objekti
juurde** talletab imporditud mõõtmised kohaliku GeoPackage’i kirjes.
[Faili vorming ja ühikud](docs/LISA5_MEASUREMENTS.md).

English: Annex 5 basement logs can import probe and sample density,
magnetic susceptibility and structural readings from CSV, TSV or Excel.
Save readings to the local object or use them only in the report preview.

## Eelmise versiooni märkused: 3.49.3

**Ekspordi → Kohalike andmete ETL-eksport → Kontrolli valikut** kontrollib
salvestatud andmeid enne, kui küsitakse failide kausta. Kontroll näitab
objekti, tabelit ja võimalusel rida. Kattuvad või vigased sügavusvahemikud
ja liitüksusel puuduv konkreetne ülemine või alumine indeks takistavad
eksporti. Lüngad, puuduolev metainfo ja varasemad väärtused mittekohalduvates
lahtrites on hoiatused: nende korral saab eksportida mustandi. Kontroll
ei paranda kirjeid ega asenda EGT-laaduri kontrolli.

**Kohalikud andmed → Litotulp…** sisaldab Lisa 5 näidistel põhinevat
pealiskorra ja aluskorra kujundust. Mõlemad on 285 mm laiad pikad lehed;
kõrgus sõltub sügavusvahemikust ja mõõtkavast. Paigutus kasutab kohaliku
objekti andmeid. Puuduvate mõõtmiste asemele väärtusi ei arvutata ja näidise
andmeid ega logo üle ei kanta. Varasem A4-paigutus on endiselt valitav.

English: Check selected local records before ETL export. Errors block file
creation; warnings allow a draft. Annex 5-style lithology logs add two
285 mm wide, depth-scaled layouts alongside the existing A4 options.

## Eelmise versiooni märkused: 3.49.2

**Kohalikud andmed → Redigeeri… → Geoloogiline kirjeldus** rakendab vana
Faktika valikureegleid rea kaupa. Genees on muudetav ainult pinnakatte ja
litoloogia täiend ainult aluspõhja real. Kihistiku valik sõltub indeksist.
Kui indeksiks valida **Liitüksus**, asendavad tavalise kihistiku valikut
ülemine ja alumine indeks koos oma kihistikuvalikuga. Hallides lahtrites
säilivad olemasolevad väärtused. Portali andmeid ega õigusi ei muudeta.

English: The local geology editor restricts genesis to cover units and
lithology qualifiers to bedrock, filters members by index, and exposes
separate upper and lower indices and members for compound units.

## Eelmise versiooni märkused: 3.49.1

**Kohalikud andmed → Redigeeri…** avaneb eraldi liigutatavas aknas. Mustandi
kõrval saab kasutada QGIS-i kaarti ning vaadata teiste objektide andmeid ja
kirjandust. Kui avatud kirje muutub vahepeal näiteks impordi tõttu, ei kirjuta
vana mustand värskemat kirjet üle.

Üldandmete ja seotud tabelite valikloendid põhinevad kaasasoleval ETL6/7/8/10
klassifikaatorite koopial ega vaja Portali ühendust. Tabeli klassifikaatoriga
lahtris avaneb valik topeltklõpsuga. Kuvatakse nimetus; uue valiku
salvestamisel kasutatakse malli koodi. Klassifikaatorist puuduvat algset
väärtust ei asendata automaatselt, ka siis, kui üksuse tüüpi muudetakse.
Vana Faktika redaktori reeglite võrdlus on kirjas failis
[Kohaliku ETL-redaktori reeglid](docs/LOCAL_ETL_EDITOR.md).

English: The local editor is a movable, non-modal window. Offline ETL6/7/8/10
selectors show the official names and save the codes, preserving untouched
source values. The EGT Portal remains read-only.

## Eelmise versiooni märkused: 3.49.0

## Litotulbad ja laboriandmed

**Kohalikud andmed → Litotulp…** avab valitud objekti trükivaate. Seal saab
valida sügavusvahemiku, vertikaalse mõõtkava ning A4 püst- või rõhtpaigutuse.
Litoloogia, üksuse indeks, piirid ja kirjeldused tulevad kohaliku objekti
andmetest. Värvid, kivimimustrid, legend, proovi- ja analüüsirada on
lülitatavad. Kui XRD tulemused on protsentides ja seotud üheselt kindla
sügavusega, saab kuvada ka koostiserada. Mõõtmata jääk jääb tühjaks.
Pikk läbilõige jaotub korduva päisega lehtedeks. Joonise saab
eksportida PDF- või SVG-failina. Valikuline gammalogi loeb **CSV** veerge
`depth,value` (või `sügavus;väärtus`), sügavus meetrites. Logi ühik tuleb
määrata faili andmete järgi; puuduva mõõtmise asemele andmeid ei tuletata.

**Kohalikud andmed → Redigeeri… → Laboriandmed** haldab prooviseeriaid,
proove, seoseid, mõõtmisi, viiteid ja analüüsitulemusi. Seotud rea saab
lisada otse valitud algkirjelt. Tulemuse väärtus, ühik, erimärk ja
määramispiirid jäävad eraldi väljadele. Paneelis **Impordi** võib ETL7/8
valida koos ETL6/10-ga või lisada olemasolevale kohalikule objektile, kui
ID-viide on ühene. Eelvaade ei muuda tööruumi ja salvestamisel ei kirjutata
üle vahepeal muudetud kirjet. **Ekspordi** paanis lisa soovi korral ETL7/8
failid koos ETL6/10-ga. Qeoloogi ajutised ID-d ei ole EGT andmebaasi GUID-id;
paketi vastuvõttu EGT laaduris pole kontrollitud.

English: **Local data → Lithology log** previews depth-scaled, paginated
PDF/SVG logs with lithology, patterns, descriptions and available sample and
analysis tracks. Add a separate gamma CSV only when those readings are available.
**Laboratory data** adds linked local sample series, samples, measurements,
references and results, with ETL7/8 import and export. All edits remain local.

## Eelmise versiooni märkused: 3.48.0

## Kohalikud objektid ja ETL

**Kohalikud andmed** kasutab Läbilõigete olemasolevat GeoPackage’i tööruumi.
Loo või ava töökaust, vali **Uus objekt…** või ava EGT, SARV või VEKA
objekt ja vajuta **Kopeeri kohalikuks**. Üldandmeid, geoloogilisi üksusi,
vahekihte, mineraale, fossiile/detriiti ja nähtusi saab muuta lokaalses
redaktoris. Pooleliolevad kirjed jäävad tööruumi mustandina. Kohaliku
objekti saab lisada koondläbilõikele. GeoPackage ja selle varukoopiad
sisaldavad ka kohalikke objekte. Avalikke lähteandmeid ega Portalit ei muudeta.

Originaalkihilt avades on kohalik koopia **Objekti andmed → Originaal / Muudetud**
valikus. Tööruumist avades saab kopeeritud objekti võrrelda salvestatud algseisuga.
**Detailvaade → Veerud…** säilitab senised vaikeveerud; peitmise või lisamise
valik salvestatakse tabelipõhiselt. Kopeeritakse ainult nähtavad veerud.

**Impordi** paanis vali ETL6 `.xlsx` (objektid) ja vajadusel korraga ka ETL10
`.xlsx` (geoloogia ja alamtabelid). Eelvaade näitab seoseid ja hoiatusi.
Sidumata ridu ei jäeta välja ning kordusimport ei kirjuta üle olemasolevaid objekte.
**Ekspordi → Kohalikud andmed: ETL6 ja ETL10** ekspordib valitud objektid
samade andmetabelite ja veergudega. Tööruumi koordinaadid on EPSG:3301
(X = idasuund, Y = põhjasuund); kõrgussüsteem tuleb teada enne absoluutpiiride
arvutamist. Tühje välju ei asendata oletustega. Ekspordi mustand ei ole
EGT-laaduris kontrollitud üleslaadimispakett.

English: **Local data** adds editable local records or copies of public EGT,
SARV and VEKA objects to the existing GeoPackage workspace. Inspect the live
original and the local version separately, or view the captured original
offline. **Detail view → Columns** changes the visible columns without altering
their defaults. **Import** previews ETL6/ETL10 Excel files before committing;
**Export** writes the selected local objects to the corresponding data sheets.
No edits are sent to public services or the EGT Portal.

## Eelmise versiooni märkused: 3.47.1

**Kihid → Kaardisildid** all saab sügavuse sisse lülitada eraldi EGT
puuraukudele (PA), vaatluspunktidele (VP), VEKA kaevudele ja SARV punktidele.
VEKA sildile saab lisada registrikoodi ning SARV sildile numbri. Vaatluspunkti
sügavus on objekti enda pikkus, mitte veesügavus. SARV puursüdamik näitab
enda sügavust või sügavusvahemikku, mitte seotud lokaliteedi sügavust. Puuduva
väärtusega rida jääb ära. Vanema SARV kihi puhul eemalda see ja lisa SK nupust uuesti.

English: **Layers → Map labels** provides separate depth switches for EGT
boreholes and observation points, VEKA wells and SARV points. You can also
display VEKA registry codes and SARV numbers. Recorded SARV drill-core depth
ranges remain ranges. Missing values are omitted.
Reload older SARV layers to show verified drill-core depths.

## Paljandi muutmine otse joonisel

Vali **Läbilõike objektid** tabelist kohalik paljand, mis on kuvatud
nimelisel läbilõikel, ja vajuta **Muuda joonisel**. Valitud tööriist määrab
hiiretoimingu:

- **Vaatlus**, **Proov**, **Foto** või **Biotsooni leiupunkt**: klõpsa tulbal
  sobival kõrgusel ning sisesta andmed. Foto/manus kopeeritakse töökausta
  alles paljandi salvestamisel.
- **Varjatud vahemik**: lohista üle lõigu. Vali põhjuseks näiteks
  varingurusu. Joonis viirutab vahemiku, kuid ei kirjuta litoloogiat üle
  ega täida puuduvaid andmeid.
- **Seinaprofiil**, **Eend**, **Süvend**, **Varingurusu ala**: klõpsa
  eraldi seinaprofiili rajale tipud järjest. Enter lõpetab, Esc katkestab
  poolelioleva toimingu. Mõõdetud raja horisontaaltelg näitab nihet
  lähtejoonest meetrites; skemaatilise raja nihked ei ole mõõdud.
  Üleulatuse puhul võivad mitu tippu olla samal kõrgusel.
- **Vali ja lohista**: nihuta punkti, vahemiku piiri, tippu või silti.
  Sildi lohistamine ei muuda punkti kõrgust. Paremklõps pakub kirje
  muutmist (sh täpsed arvväärtused) ja eemaldamist. **Võta tagasi**,
  **Tee uuesti**, **Salvesta paljand** ja **Katkesta** haldavad muudatusi.

Salvestatud paljand ja aktiivne läbilõige uuenevad korraga; andmebaaside
algkirjed ning teised varem salvestatud läbilõiked ei muutu. Joonise
radade nähtavust saab lülitada ning SVG/PDF kasutab samu kuvaseadeid.

Biotsoonide leiud on vaikimisi punktid. Leiupunkti saab kasutada
korrelatsiooni ankruna; sama kõrgusega leiud paiknevad kõrvuti.
Vanad **Tõlgendatud biotsoonide ulatus** intervallid säilivad ja on
vaikimisi peidetud. Neid ei teisendata automaatselt punktideks. CSV
leiupunktide rada kasutab päiseid
`position,taxon,zone,sample_ref,source_ref,note`.

English: select a local outcrop and use **Edit drawing** to add or drag
observations, biozone occurrences, obscured intervals and ordered wall
vertices. Measured and schematic geometries use separate lanes. Existing
interpreted biozone ranges are preserved but hidden by default; they
are not evidence points. Save writes only to the local workspace.

## Eelmise versiooni märkused: 3.46.0

## Kohalik läbilõigete tööruum

1. Ava **Läbilõiked → Ava läbilõikeaken → Tööruum → Loo töökaust…** ja vali
   endale leitav kaust. Sinna tekib `qeoloog_sections.gpkg`. Projekti senine
   avalikest allikatest koostatud läbilõige saab esimeseks nimeliseks kirjeks.
   Ilma töökaustata jääb senine projektipõhine töövoog alles.
2. Menüüst **Läbilõige** saad luua uue joonise, dubleerida olemasoleva ja
   kopeerida teise joonise kujunduse. Vali joonis akna ülemisest loendist.
3. Lisa kaardilt või otsingust **EGT, SARV või VEKA** objekt. **Tulbad → Ava
   valitud tulba algkirje** avab ID järgi vastava objekti laaditud kihis või
   veebikirje, kui selleks on olemas avalik ID. Tööruumi saab kasutada ka
   võrguühenduseta; andmebaase ei muudeta. MaRu ja autentitud Portali
   objekte uude tööruumi ei kopeerita.
4. **Tulbad → Lisa kohalik tulp või paljand…** avab kihitabeli. Nullpunkti ja
   paljandi joone saad valida kaardilt. Andmebaasi tulba redigeerimine teeb
   kohalikku teeki koopia, mis säilitab algkirje viite. Kui lisad sama tulba
   teisele joonisele, salvestab see joonis oma versiooni; hilisem muutmine
   ei kirjuta varasemaid jooniseid üle.
5. **Kujundus** võimaldab valida StrataPy-laadse või klassikalise stiili,
   muuta tulba laiust, legendi ja radade järjekorda. Kujundus on Qeoloogi
   enda joonistajas ega nõua StrataPy installimist. Joonise saab eksportida
   SVG/PDF-i.

### Ristlõige, mõõdetud tulp ja korrelatsioon

- **Kaardijoone järgi**: objektid on piketi ja tegeliku absoluutkõrguse
  järgi. Kaardile märgitud paljandit saab kaasata ka selle joongeomeetria
  alusel. Paljandi mõõtelõik ise ei määra nullpunkti absoluutkõrgust.
- **Suhteline kõrgus / sügavus**: alt üles mõõdetud paljand ning ülalt alla
  mõõdetud puurauk kuvatakse kumbki oma nulltaseme suhtes. See režiim sobib,
  kui absoluutkõrgus või vertikaaltegur pole teada. Absoluutvaates peab
  kõigil objektidel olema sama kõrgussüsteem; Qeoloog ei teisenda tundmatut
  kõrgussüsteemi ega eelda kaldu mõõdetud paljandi paksust vertikaalseks.
- **Korrelatsioon**: vali igas võrreldavas tulbas ankur, mille järgi see
  joondatakse. **Lisa korrelatsioon…** seob kindlad piirid või mõõtepunktid.
  Oletuslik seos on katkendjoonega. Algandmed, kõrgus ja kaardiasukoht ei muutu.

Tulba redaktor impordib UTF-8 CSV/TSV-andmeid iga raja jaoks eraldi. Näiteks:

| Rada | Põhilised päised |
| --- | --- |
| Kihid | `top,bottom,lithology,index,contact,grain_size,note` |
| Isotoobid | `position,analyte,value,unit,reference,uncertainty,sample_ref,source_ref,gap_before` |
| Biotsoonid ja lademed | `top,bottom,name,scheme,source_ref` |

Isotoobikõverad eristatakse näitaja, ühiku ja võrdlusskaala järgi. Tühja
mõõtmise või `gap_before=1` korral katkeb kõver; kujunduses saab valida ka
maksimaalse vahe. Mõõtepunkti topeltklõps avab mõõtmise andmed ja viited.

### Varundamine ja taastamine

**Tööruum → Varundamise seaded…** määrab töökaustast eraldi asukoha ning
valikulise automaatse varundamise (viimased kümme kontrollitud koopiat).
**Tee varukoopia kohe** teeb ajatempliga koopia andmebaasist ja manustest.
**Taasta koopiast…** kontrollib koopia terviklust ja loob uue kausta,
olemasolevat tööruumi üle kirjutamata. Töökausta tõstmisel kopeeri kogu
kaust ning kasuta **Ava olemasolev töökaust…**. GeoPackage’i tabel on
loetav ka ilma Qeoloogita; interaktiivne joonis avaneb pluginas.

English: **Sections → Workspace** stores named drawings, local borehole and
outcrop logs, attachments and view settings in a user-selected GeoPackage
workspace. Public EGT, SARV and VEKA references survive offline editing and
backup/restore. Native StrataPy-inspired and classic styles support isotope,
biozone and regional-stage tracks, explicit datum alignment and manually
confirmed correlations. Backups are optional, separate from the workspace,
and restore to a new folder. Existing project-only sections still work.

## Eelmise versiooni märkused: 3.45.3

**Kihid → Kaardisildid → EGT sildi sisu:** veerus **Puuraugud (PA)** saab
valida **Puuraugu sügavus**, kas eraldi või koos nime ja teiste sildiridadega.
Näide: `Sügavus: 169,1 m`. Kasutatakse puuraugu pikkust (`pikkus`), selle
puudumisel vertikaalset ulatust (`vertikaalne_ulatus`). Puuduva väärtuse korral
jääb rida ära. Valik on vaikimisi väljas ja ei vaja lisapäringuid.

English: under **Layers → Map labels**, select **Borehole depth** for EGT
boreholes to show the recorded length (or vertical extent if unavailable).
It can appear alone or alongside other labels; missing depths are omitted.

## Eelmise versiooni märkused: 3.45.2

Läbilõikeakna horisontaalne suum töötab nüüd nii `Shift` + kerimisrattaga
kui ka puuteplaadi horisontaalse liigutusega, sh ainult pikslipõhiste sündmustega.
`Ctrl`/`Command` + kerimine muudab jätkuvalt ainult vertikaalset mõõtkava;
tavaline vertikaalne kerimine liigutab vaadet. Suum töötab ka joonise ümber
oleval tühjal alal. Kasutaja horisontaalset mõõtkava ei kirjutata automaatse
miinimumvahega üle ning valik säilib projektis. Väljasuumimisel väheneb ka
keritava joonise tegelik laius.

English: combined-section horizontal zoom now supports Shift + wheel and native
horizontal touchpad/wheel gestures, including pixel-only events and viewport
margins. Ctrl/Command + scroll changes only vertical scale; ordinary vertical
scroll still pans. Manual horizontal scale overrides automatic initial spacing,
survives refresh/project restoration and shrinks the scrollable canvas on zoom-out.

QA: [2026-11-16](docs/QA_2026-11-16.md).

## Eelmise versiooni märkused: 3.45.1

Parandatud on kolm Läti WFS-kihti: karstialad (LKR), geoloogilised rikked
(LRK) ja seismilised profiilid (LSP). Need kasutavad nüüd LVĢMC ametlikku
otseühendust. Vanad sisseehitatud teenuseaadressid uuendatakse seadetes ja
projektikihtides; kohandatud teenuseid ning kasutaja nuppude paigutust ei muudeta.

Fondiala laadimisel kontrollitakse aruande ID-d ja teenuse muutumist, välditakse
eelmise projekti hilinenud vastuste rakendamist ning piiratakse geomeetriapuhvri
suurust. Ala- ja filtrinupud on kontrollitud pärisaruannetega ning filtri
taastamisega pärast QGIS-i taaskäivitamist.

English: the three Latvian geology WFS layers now use the official LVĢMC
geology workspace. Saved built-in settings and old project sources migrate
without resetting custom endpoints or toolbar choices. Archive-area loading
now validates report identifiers, separates caches by service, ignores stale
project responses, handles explicitly declared CRS and uses a bounded cache.
The real-service area/filter controls and cold-start project restoration were
retested. Portal access remains read-only.

QA tulemused: [QA 2026-11-10](docs/QA_2026-11-10.md).

## Fondiala nupud (lisatud versioonis 3.45.0)

Puuraugu **Üldandmed → kande_alus_nr** juures on kolm uut nuppu:

- **Aruande ala** lisab/eemaldab ainult selle fondiaruande uuringuala piirjoone.
- **PA filter** piirab avalike EGT puuraukude kuvamist aruande tegeliku ruumikuju
  järgi. Sama aruandenumber ei pea puuraugu andmetes esinema. Olemasolevad
  kategooria-, indeksi- ja otsingufiltrid rakenduvad edasi AND-loogikaga.
- **×** eemaldab ainult fondiala filtri. Ruumikuju ja muud filtrid jäävad alles.

Piirjoon ja filter on sõltumatud: ala võib eemaldada ka aktiivse filtri korral.
Filtrisse arvestatakse kõiki aruande pindobjekte, sh lahusosi ja auke; pelgalt
ümbritsevat ristkülikut ei kasutata. Ala piirile jäävad punktid on kaasatud.
Fondi ruumifilter säilib QGIS-i projektiga; puuduvat või poolikut ruumikuju ei
rakendata filtrina. SARV, MaRu, VEKA ja Portali kihtidele see PA-filter ei laiene.

English: beside **Object data → General → kande_alus_nr**, **Report area** toggles
the selected archive report's outline. **BH filter** restricts public EGT
boreholes to the report's actual polygon(s), independently of the outline and
in addition to existing filters. **×** clears only this spatial filter. Polygon
holes and disjoint parts are respected, boundary points are included, and the
filter is restored with the QGIS project. Portal data remains read-only.

Varasema versiooni QA: [QA 2026-11-09](docs/QA_2026-11-09.md).

## Eelmise versiooni märkused: 3.44.2

3.44.2 parandab QA käigus leitud 15 viga: koondläbilõike taastamine,
tiheda joonise eksport, DEM-i andmelüngad, vastuolulised SARV seosed,
teenuste lehekülgede täielik laadimine, detailvaate lingid ja eluiga,
filtritega kooskõlaline infotööriist, numbriliste ID-de kuvamine,
MaRu seose kohene puhastamine, tühjad rajad, indeksite värvid ja pikad
kirjeloendid. Tiheda koondläbilõike ühtlast horisontaalmõõtkava suurendatakse
loetavuse tagamiseks automaatselt; SVG/PDF kasutab vajadusel laiemat lehte.
Objektide tegelikke pikette eraldi ei nihutata.

Vanad VEKA veebilehelt vaadatud veeanalüüsid lisanduvad sama seansi
näitajavalikusse ning on filtris ja ekspordis kasutatavad. See ei tähenda,
et kõigi Eesti kaevude vanad veebilehed oleks ette alla laaditud. Tulemusteta
või eri ühikuperekonnaga näitajaid ei samastata oletuslikult.

English: 3.44.2 addresses the fifteen QA findings, including saved-section
restoration, readable wide SVG/PDF exports, explicit DEM gaps, conservative
SARV conflict handling, complete collection pagination, detail-view links and
widget cleanup, filter-aware identify, numeric identifiers and stratigraphic
range colours. Large record groups use a searchable scrolling dialog. Legacy
VEKA chemistry viewed during the current session is available to parameter
selection, filtering and export; this is not a country-wide legacy-data crawl.

**Objekti andmed** paanis asub **Detailvaade** kõrval nupp **Mine asukohta**,
mis viib kaardi vaadeldava objekti juurde ja säilitab senise mõõtkava.
Asukohaandmete puudumisel on nupp mitteaktiivne. Ühise otsingu vaikimisi
allikas on **EGT**; ka **Lähtesta** taastab selle valiku.

In **Object data**, **Go to location** beside **Detailed view** centres the
map on the current object while preserving its scale. The button is disabled
when no location is available. Search initially uses **EGT**, and **Reset**
restores that source.

Qeoloog on QGIS 4 rakendus EGT GEA ja SARV geoloogiaandmete ning EELIS/VEKA
puurkaevuandmete kuvamiseks, seostamiseks ja uurimiseks. Lisaks saab avada ja
seadistada Maa- ja Ruumiameti (MaRu) ning teiste avalike andmeallikate WMS/WFS
teenuseid. Qeoloog kasutab ka MaRu ametlikku ajaloolise puursüdamike
andmebaasi allalaadimist, mille kirjed seotakse EGT puuraukudega.

**LK → Geoloogia → GTK** sisaldab Soome geoloogiateenistuse ametlikke avalikke
WMS/WFS-kihte. Valikus on aluspõhja litoloogilised üksused ja rikked
1:200 000, pinnakatte põhja- ja pindmine kiht 1:50 000, aeromagnetiline ja
aeroradiomeetriline kaart ning WFS-vaated aluspõhja vaatlustele, puurimistele,
riiklikule puursüdamikuarhiivile, mineraaliesinemistele ja
ehitusgeoloogilistele uuringupunktidele. GTK kihid küsitakse nende ametlikus
EPSG:3067 koordinaatsüsteemis ning QGIS projitseerib need projekti CRS-i.
GTK WMS-i legendid kuvatakse valgel taustal, et nende must tekst oleks loetav
ka QGIS-i tumeda kasutajaliidese teemaga; kaardikihid ise jäävad läbipaistvaks.
Qeoloogi **i**-nupp avab nii GTK WFS-objekti atribuudid kui päringut toetava
GTK WMS-kaardi klikitud koha `GetFeatureInfo` andmed. Tulemused kuvatakse
Qeoloogi kopeeritavas detailvaates.
Teenuste aadressid pärinevad GTK ametlikust rajapintade kataloogist:
https://www.gtk.fi/en/services/data-sets-and-online-services-geo-fi/interface-services/
Teenuste kasutamisel kehtivad GTK avaldatud kasutustingimused.

**LK → Geoloogia → Läti** sisaldab LVĢMC ja GeoLatvija ametlikke avalikke
kihte. Valikus on aluspõhja geoloogiline kaart ja Kvaternaari kaart
1:200 000, geoloogilised puuraugud, karstialad, rikked, seismilised profiilid,
põhjaveekogumid ning eraldi **Maavarad** alammenüüs maavarade leiukohad,
kaevandamisload ja kaevandamislimiidid. Läti puuraugud on ühise
**Otsing ja filtrid** paani all allikana **Läti LVĢMC** otsitavad nime,
andmebaasinumbri, aasta ja eesmärgi järgi. Qeoloogi **i**-nupp avab Läti
vektorkihtide atribuudid ja päringut toetavate WMS-kaartide `GetFeatureInfo`
tulemused kopeeritavas detailvaates.

Avalik Läti puuraugukiht annab praegu 181 punkti koos nime/numbri, rajamise
aasta, koordinaatide ja rajamise eesmärgiga. Teenus ei avalda nende punktide
geoloogilisi läbilõikeid ega puursüdamiku kastipilte, seetõttu Qeoloog neid
Läti puuraukude detailvaates välja ei mõtle ega asenda mõne teise allika
andmetega. Kihid kasutavad teenuste native CRS-e EPSG:3059 või EPSG:4258 ja
QGIS projitseerib need projekti koordinaatsüsteemi.

Ametlikud lähtepunktid:

- https://geodata.lvgmc.lv/server/rest/services
- https://data.gov.lv/dati/eng/dataset/annex-ii-inspire-dataset-for-geology-theme-wfs
- https://data.gov.lv/dati/dataset/eoloiskie-un-hidroeoloiskie-urbumi-wfs
- https://data.gov.lv/dati/eng/dataset/derigo-izraktenu-iznemot-pazemes-udenu-atradnes-pases

## Kihikataloog ja MaRu puursüdamikud

**Kihid** paani **Kihikataloog** otsib kõiki seadistatud kihte koodi, nime,
teenuse, kihi nime või URL-i järgi. Loendit saab piirata teenusetüübi,
kodurühma ja lubatud/keelatud oleku järgi. Filtreeritud loendis säilivad
kihikataloogi sisse-välja lülitamine, redigeerimine, eemaldamine ja järjekorra
muutmine.

Vaikekataloogi **MP – MaRu puursüdamike andmebaas** laadib Maa- ja
Ruumiameti ametliku avaliku ZIP-väljavõtte ja loob sellest QGIS-i
kasutajaprofiili kirjutuskaitstud SQLite-otsinguindeksi. Väljavõtet ei lisata
plugina ZIP-paketti; selle saab **Kihid** paanis eraldi uuendada. MP kiht kuvab
ajaloolise andmekogu punktid ning neid saab kaardilt avada, otsida ja
koondläbilõikele lisada.

EGT puuraugu `ma_orig_id` seotakse sama MaRu `pa.id` kirjega. Kui ametlik ID
puudub, kinnitatakse automaatne vaste ainult siis, kui korraga sobivad number,
kirjeldav nimi ja kuni 500 m asukohalähedus. Näiteks seotakse nii MaRu 1498
**735 Mustvee**, EGT GEA 194350 ja SARV lokaliteet 23365, samas kauge sama
numbriga objekt jäetakse kõrvale. Ebaselged vasted jäävad kandidaatideks.

Seotud vaates liidetakse MaRu üldandmed, geoloogiline kirjeldus,
puursüdamikukastid ja kastipildid, proovid ning proovipildid. EGT jääb
läbilõike esmaseks allikaks ja MaRu kirjeldus täidab ainult EGT kirjeldusse
jäänud sügavusvahemikud. Läbilõike päises saab EGT ja MaRu kirjeldust,
kastipiire ning proove allikate kaupa eraldi sisse või välja lülitada. MaRu
allikast täidetud intervall on joonisel allikatähisega eristatav. Mitme
allika kastid joonistatakse litoloogiatulbal kõrvuti: EGT kastid tähisega
**K**, SARV kastid tähisega **S** ja MaRu kastid tähisega **M**. Iga rada
viirutatakse eraldi seal, kus selle allika kast puudub. MP
kaardipunktid kasutavad samu pinnakatte, aluspõhja, aluskorra ja teadmata
kategooriaid nagu EGT punktid. Kõik MaRu lähteväljad on nähtavad eraldi
kirjutuskaitstud detailvaate tabelites.

MaRu kirje avamisel kontrollitakse ametlikku ID-d ning turvalist
nime/numbriga ruumilist vastet otse avalikust EGT WFS-ist ka siis, kui PA/VP
kihti ei ole projekti laaditud. Ühese kinnitatud vaste korral avaneb EGT,
MaRu ja võimaliku SARV vaste ühendvaade; mitme vaste korral ei valita ühtki
oletuslikult.
MaRu proovifotod on klikitavad ka läbilõikel. **Manused** paanis kuvatakse
proovifoto sügavus, lähteandmete järgi arvutatud absoluutkõrgus, indeks,
litoloogia ja muu algne metaandmestik. Absoluutkõrgust ei märgita EH2000
väärtuseks, sest vanema kirje kõrgussüsteem ei pruugi olla teada.

Manused on rühmitatavad allika järgi (**EGT**, **MaRu**, **SARV** ja
**EGT Portal**). MaRu kastifotod jäävad vaikimisi **Puursüdamik** paani, et
neid ei näidataks kahes kohas; soovi korral saab need linnukesega ka Manuste
tabelisse lisada.

MaRu geoloogilise kirjelduse negatiivne `D` tähistab viimast üksust, mille
alumist piiri puurimisega ei läbitud. Qeoloog kasutab selle intervalli
paksusena `abs(D)` ja lisab indeksile `+` märgi. Vigase ümberpööratud
kastisügavuse korral ei joonistata kasti tagurpidi; algne väärtus säilib
detailvaates ning kasti saab kohaliku parandusega korrigeerida. MaRu otsing
hõlmab lisaks üldandmetele geoloogilisi kirjeldusi, kaste ja proove. Proovi
asukohaviidet saab eraldi filtreerida ning see kuvatakse **Proovid** tabelis
lingina seotud MaRu puuraugu juurde.

**MaRu seose haldus** lubab EGT objekti MaRu ID-d lisada või ümber siduda,
algse `ma_orig_id` seose vigaseks märkida ja kohaliku paranduse eemaldamisel
EGT algse seose taastada. Käsitsi sisestatud ID kontrollitakse kohaliku
ametliku väljavõtte vastu. Parandus salvestatakse ainult QGIS-i
kasutajaprofiili ega muuda EGT või MaRu lähteandmeid. **Kihid** paani
**Ekspordi SARV ja MaRu seosed** kirjutab mõlemad seoseliigid koos vigaste
lähte-ID märgetega CSV- või JSON-faili.

## Kirjutuskaitstud detailvaade

Kaardilt valitud objekti **Objekti andmed** päises olev **Detailvaade** avab
eraldi suure akna. **Üldandmed** näitab ainult täidetud välju ning kuvab
inimloetava väärtuse kõrval vajaduse korral algse koodi, tehnilise väljanime
ja andmeallika. Kõik mitte-tühjad seotud andmed (puursüdamik, proovid,
analüüsid, eksemplarid, manused, kirjandus ning VEKA konstruktsioon,
pumpamiskatsed ja veekeemia) avanevad oma tabelina.

Aktiivsest tabelist saab teksti otsida, linke topeltklõpsuga avada ning
valitud read, aktiivse tabeli või kogu detailvaate TSV-kujul lõikelauale
kopeerida. `Ctrl+C` (macOS-is `Command+C`) kopeerib valitud read; kui valikut
pole, kopeeritakse aktiivne tabel. Seotud andme rea topeltklõps avab selle
kirje kõik täidetud lähteväljad; lingilahtri topeltklõps avab lingi. Vaade ei
sisalda ühtegi muutmis- ega salvestamistoimingut ning töötab ühtmoodi avalike,
VEKA, SARV ja sisselogitud EGT Portali objektidega.

## EGT ArcGIS Portal (kirjutuskaitstud)

Qeoloog saab lisada avalikke ja autentimist nõudvaid ArcGIS FeatureServeri
kihte ainult vaatamiseks. Autentimine jääb
QGIS-i krüpteeritud autentimisandmebaasi; Qeoloog salvestab oma seadetes ainult
valitud `authcfg` tunnuse ega talleta kasutajanime, parooli või OAuthi tokenit.

Kõik Qeoloogi kaudu avatud Portali kihid märgitakse QGIS-is kirjutuskaitstuks.
Portali objektide lisamise, muutmise, kustutamise ja välitööde üleslaadimise
nuppe ei kuvata ning kõik varasemad kirjutamisteed on rakenduse ja
võrgupäringu tasemel blokeeritud. Sisselogimine, kataloog, kaardikihid,
serverilegendid, objektiandmed, manused, kaardisildid ja läbilõiked säilivad.

1. Ava **Qeoloog → Kihid → EGT Portal** ja vajuta
   **Ühenda EGT Portaliga**.
2. Esimesel korral sisesta EGT sisejuhendis olevad **Client ID** ja
   **Client secret**. Qeoloog täidab ise Authorization Code voo, päringu- ja
   tokeniaadressi, suunamise ning `X-Esri-Authorization` päise ja salvestab
   konfiguratsiooni QGIS-i autentimishoidlasse. Järgmistel kordadel seda
   dialoogi enam ei näidata.
3. Brauseris avaneb tavaline EGT Portali sisselogimine. Eduka sisselogimise
   järel kuvab Qeoloog aktiivse kasutaja nime ja loeb automaatselt sisse kõik
   sellele kontole nähtavad Feature Service'id.
4. Nupureal avaneb **EGT** menüü kohe **LK** kõrval. Teenused on rühmitatud
   juurdepääsu järgi (**Minuga jagatud**, **Organisatsioon**, **Avalikud**) ja
   nende sees ArcGIS REST-i teenusekaustade järgi.
5. Ava soovitud teenus ja märgi üks või mitu alamkihti. Alamkihtide loend
   küsitakse serverist alles teenuse avamisel, seega jääb suur kataloog
   kiireks. Uus klõps linnukesel eemaldab kihi projektist.

Qeoloog ei alusta sisselogimist QGIS-i käivitamisel. OAuthi brauseriaken avaneb
ainult siis, kui kasutaja vajutab ühendamise või Portali kataloogi
värskendamise nuppu. Seetõttu saab QGIS-i avada ka aeglase või puuduva
Portaliühenduse korral.

Portali kihile rakendatakse automaatselt FeatureServeris avaldatud EGT
standardlegend. Nii säilivad muu hulgas stratigraafiliste indeksite värvid,
rikete jooneviisid, kategooriate nimetused ja erisümbolitena avaldatud
punktmärgid. Kui mõnda ArcGIS-i sümbolit ei õnnestu teisendada, jääb alles
QGIS-i AFS-andmepakkuja enda loetud serveristiil.

Olemasoleva autentimiskonfiguratsiooni käsitsi valimine ja QGIS-i täielikud
autentimisseaded on vajaduse korral endiselt kättesaadavad valiku
**Täpsemad sätted** all.
FeatureServeri URL-i käsitsi lisamise võimalus jääb alles kohandatud või
kataloogist puuduva teenuse jaoks.

Samas peidetud jaotises saab sisse lülitada valiku **Kuva Faktika testserver
EGT menüüs**. Vaikimisi on see välja lülitatud. Sisselülitamisel ilmub EGT
menüüsse oranži hoiatusikooniga eraldi **Faktika testserver**, mis kasutab
fikseeritud teenust
`https://testgis.egt.ee/arcgis/rest/services/Test_Faktika_t%C3%B6%C3%B6kiht/FeatureServer`
ja valitud QGIS-i autentimiskonfiguratsiooni. Testserveri punktikiht ning
seotud tabelid avatakse eraldi grupis kirjutuskaitstult ning kasutavad
domeenide REST-päringuid, kaardisilte, objektiandmeid ja läbilõike tuge.

Testteenuse kihi- ja tabeli-ID-d loetakse sisselogimisel teenuse enda REST-
metainfost ning seotakse Faktika rollidega nime järgi. Seetõttu ei eeldata, et
testteenuse numeratsioon kattub tootmisteenusega.

Kui ArcGIS FeatureServeri kihti ei saa avada, teeb Qeoloog sama QGIS-i
autentimiskonfiguratsiooniga eraldi kirjutuskaitstud REST-kontrolli. Veateates
kuvatakse ArcGIS-i veakood ja kirjeldus või kihi tüüp, geomeetria ning väljade
arv; OAuth-tokenit ega täielikku serverivastust logisse ei kirjutata.

### Arhiveeritud redigeerimisreeglid

Alates versioonist 3.37.0 on allpool kirjeldatud Portali redigeerimistöövood
rakenduses välja lülitatud ja nende nuppe ei kuvata. Kirjeldused on säilitatud
ainult tulevase eraldi kooskõlastatud lahenduse tehnilise arhiivina; aktiivse
versiooni kaudu ei saadeta Portalisse ühtegi muudatust.
Täielik tehniline ülevaade on failis
[`docs/PORTAL_EDITING_ARCHIVE.md`](docs/PORTAL_EDITING_ARCHIVE.md).

QGIS avas varem kihi oma ArcGIS FeatureServeri andmepakkujaga. Kui sisselogitud
kasutajale ja teenusele on lubatud `Create`, `Update` või `Delete`, ilmub
aktiivse kihi korral **Aktiivse Portali kihi redigeerimine**. Sealt saab
redigeerimise käivitada, muudatused Portalisse salvestada või neist loobuda;
geomeetria ja atribuutide muutmiseks kasutatakse QGIS-i tavalisi tööriistu.
Kirjutuskaitstud kasutajale redigeerimisnuppe ei näidata. OAuthi
kliendisaladust, kasutaja parooli ega tokeneid Qeoloogi paketis ei ole.

Sisselogitud kasutajale ilmub samasse plokki **Välitööde import →
Geofüüsika välitööd**. Töövoog loeb CSV-failist kohustuslikud `x`, `y` ja
`z` veerud, kasutab punktide failijärjekorda ning loob Portali sihtkihti ühe
Z-koordinaadiga multipart-joone. Järjestikuste punktide üle 50 m vahe alustab
uut jooneosa. Vaikimisi koordinaatsüsteem on EPSG:3301, kuid seda saab enne
üleslaadimist muuta. Nimi, kuupäev, meetod, seade, vastutaja ja märkus
küsitakse enne salvestamist; meetodi, seadme ja vastutaja valikud loetakse iga
kord otse **Geofüüsika välitööde** Portali kihi koodiloenditest. Andmed
saadetakse serverisse alles nupu **Laadi Portalisse** vajutamisel.
Selle kihi legend kategoriseeritakse alati välja `geofys_meetod` ehk
**Meetod** järgi. Reegel taastatakse ka projekti avamisel ning pärast Portali
redigeerimise salvestamist, tühistamist või CSV üleslaadimist.

Sisselogitud kasutaja **EGT** menüüs on esile tõstetud **Faktika
töökiht**. See lisab projekti sisemise `Puurauk/vaatluspunkt` PointZ-kihi
ning selle tabelid `Isik`, `Manuse märksõnad`, `Manus`, `Juurdepääsu alus`
ja `Geoloogiline üksus` eraldi gruppi. Punktikihi legend on pesastatud objekti
tüübi (puurauk, vaatluspunkt, vaatluspunkt merel) ning üksuse (pinnakate,
aluspõhi, aluskord, muu/teadmata) järgi. Faktika kasutamisel peidetakse
avalikud PA/VP kihid ajutiselt, et samu objekte ei joonistataks topelt;
Faktika sulgemisel taastatakse nende varasem nähtavus.

**Objekti andmed** paanis kuvatakse sisselogitule **Lisa objekt** ning Faktika
vaste leidmisel **Redigeeri**. Avalik ja sisemine kirje seotakse esmalt täpse
GlobalID järgi; `gea_id` on ainult kontrollitud varuvariant ning erineva
GlobalID korral kuvatakse konflikt ega avata vale kirjet redigeerimiseks.
Eraldi muudetavas aknas saab hallata PointZ X/Y/Z koordinaate, metaandmeid,
geoloogilisi intervalle, manuseid, märksõnu ja juurdepääsu aluseid.
Geoloogilise üksuse paksus ning Z1/Z2 absoluutkõrgused arvutatakse Z ja
suhteliste sügavuste põhjal automaatselt. Objekti pikkus arvutatakse viimase
geoloogilise üksuse alumise sügavuse järgi. Kihistiku valik näitab ainult
valitud indeksi alla kuuluvaid kihistikke; genees on muudetav ainult
pinnakattes ning litoloogia täiend ainult aluspõhjas. Liitüksuse korral
asendub tavaline kihistik ülemise ja alumise indeksi ning nende kihistike
valikutega. Uus rida pärib eelmiselt realt üksuse, autori, aluse ja aluse
numbri. Portali vigane kood `0` asendatakse väärtusega **Teadmata**;
kihistike erikoodid kuvatakse siltidena **Teadmata** (`997`) ja
**Ei kohaldu** (`998`). Pinnakatet ei saa lisada aluspõhja või aluskorra alla
ning aluspõhja ei saa lisada aluskorra alla. Kuupäevaväljad, sh
**Valmimise aeg**, kasutavad kalendri ja kellaajaga vormingut. Enne salvestust
kontrollitakse kohustuslikke välju, domeene, sügavuste kasvu, kattumisi,
objekti kogusügavust, pinnakatte geneesi ja liitüksuste järjekorda.
Põhiobjekt ning seotud kirjed salvestatakse ühe tagasipööratava Portali
toiminguna; vahepeal teise kasutaja muudetud kirjet ei kirjutata ajatempliga
kontrolli tõttu vaikimisi üle. Auditvälju `lisaja`,
`lisamise_aeg`, `muutja` ja `muutmise_aeg` Qeoloog ei kirjuta: ArcGIS
FeatureServeri editor tracking täidab need automaatselt sisselogitud kasutaja
ja serveriajaga. Sama kehtib ArcGIS-i standardväljade `created_user`,
`created_date`, `last_edited_user` ja `last_edited_date` kohta.
Kui redigeeritaval puuraugul puudub SARV vaste, pakub redaktor Qeoloogi
kohalikult kinnitatud seost või kuni viis sobivat kandidaati. Kinnitatud seos
valitakse ette, kuid uut kandidaati ei rakendata ilma kasutaja valiku ja
salvestamiseta. Seos salvestub Qeoloogi kohalikku seosehaldurisse ega kirjuta
Portali `sarv_id` välja varjatult üle.

SARV vaste valik paikneb kompaktselt Portali **SARV ID** väärtuse kõrval.
**Asukoha kõrguskontroll** on vaikimisi suletud lahtipakitav jaotis. Väljad
**Sügavus**, **Sügavuse viis** ja **Veealune sügavus** kuvatakse ainult mere
vaatluspunkti redigeerimisel. Liitüksuse neli eraldi veergu on koondatud
kaheks: **LÜ ülemine** ja **LÜ alumine** sisaldavad kumbki indeksi ning sellele
vastava kihistiku valikut. Indeksiga piiratud kihistikuvalikus jäävad alati
loetavalt kättesaadavaks **Teadmata** (`997`) ja **Ei kohaldu** (`998`).
Portali skeem ei avalda litoloogia ja litoloogia täiendite vahel tingimuslikke
seoseid, mistõttu Qeoloog ei rakenda neile oletuslikku jäika filtrit.
Väljad **Märkus** ja **Lisainfo** paiknevad parempoolses detailivormis ning
kasutavad mitmerealist tekstiala; märkuseväli on pikema kirjelduse jaoks
suurem.

Portali objekti redaktori **Asukoha kõrguskontroll** aitab kontrollida vana
aruande tõenäoliselt õiget Z-kõrgust võimaliku vale X/Y asukoha vastu. Valida
saab projektis avatud failipõhise DEM-i, objekti ja rastri kõrgussüsteemi ning
sobivusvahemiku. **Kuva sobivusala** lisab ajutise rohelise-kollase rasterkihi
vaadeldava Faktika punktikihi alla ja jätab väljapoole `Z ± tolerants`
jäävad pikslid läbipaistvaks. Kaardilt valitud kandidaadil näidatakse DEM-i
3×3 piksli mediaani, vahemikku, erinevust Z-st ja kaugust algasukohast.
**Määra kandidaadi X/Y** muudab ainult vormi koordinaate; Z-d ei kirjutata
DEM-i väärtusega üle ning midagi ei salvestata enne kogu objekti tavapärast
salvestamist.

Objekti Z kõrgussüsteem valitakse teadlikult väärtuste EH2000, BK77,
EUREF-EST97 ellipsoidaalne või teadmata vahel. BK77↔EH2000 ja
ellipsoidaalne↔EH2000 teisendused tehakse koordinaadist sõltuva Maa- ja
Ruumiameti ametliku mudeliteenusega. Teadmata süsteemi korral näidatakse
selget hoiatust ega teeselda teisendust. Tavalise ühekanalilise DEM-i puhul
kasutatakse automaatselt esimest kanalit; kõrguskanali valik ilmub ainult
mitmekanalilise rastri täpsemates sätetes ning valik jäetakse rastri kaupa
meelde. Kontroll on nähtav ainult EGT Portalisse sisse logitud redaktoris.

Uue Faktika objekti lisamisel saab asukoha valida kaardilt klõpsates või
kasutada kaardi keskpunkti. Põhiobjekti geoloogilise üksuse kood arvutatakse
salvestamisel üksustest automaatselt prioriteediga **aluskord → aluspõhi →
pinnakate → muu/teadmata** ning detailvaates kuvatakse koodi asemel label.
Puursüdamiku paanis saab kohalikus redigeerimisrežiimis lisada või muuta ka
kaste, nende ülemist/alumist sügavust, diameetrit, staatust ja kirjeldust.
EGT kasti staatused loetakse redaktori avamisel uuesti AUQ tabeli 22
ArcGIS REST-domeenidest ja kuvatakse koodi asemel ametliku labelina; SARV
hoiukoha valik kasutab aktiivse objekti API-st saadud hoiukohti. Kasti
sügavuse muutmisel kontrollitakse sama allika kõiki kaste. Positiivse ulatusega
kattumise korral saab avada ka kattuva kasti redaktori või kogu toimingu
katkestada; ükski muudatus ei salvestu enne, kui mõjutatud vahemikud enam ei
kattu. Ühise piiri jagamine on lubatud.
Need parandused ei muuda EGT ega SARV lähteandmeid, kuid lähevad kohalike
paranduste ekspordifaili.

EGT menüü tõstab eraldi tervikutena esile ka **EGT korrastatavad puuraugud
v2** ning **Faktika välikaardistamise**. Korrastatavate puuraukude objektid ja
viis seotud tabelit kasutavad sama Objekti andmete redaktorit nagu Faktika
töökiht. Välikaardistamise punktid ja kirjeldustabel avatakse ühe seotud
grupina ning neid saab muuta QGIS-i Portali redigeerimisnuppudega. Punkti
Portali pildimanused kuvatakse Qeoloogi **Manused** paanis ja avatakse
autenditud allalaadimise järel kohalikus pildivaaturis. Portalis
leiduvad vanemad samanimelised, kuid peatatud teenused jäetakse tavakataloogi
ega esitata toimiva töövoona.

**LK → Abikihid → Tehnorajatiste kitsenduste vööndid** (`TV`) kuvab ühes
WMS-kihis side-, elektri-, gaasi-, kaugkütte- ja veevarustuse kitsenduste
mõjualad. Allikas on Maa- ja Ruumiameti KPOIS-i avalik kitsenduste vööndite
teenus. Kihti saab Kihid-paanil sisse/välja lülitada või nupureale tõsta.
See kuvab kitsenduste vööndeid, mitte tehnovõrkude täpseid trassijooni.

**LK → Geoloogia** valikus on ka EGT **Aluspõhja kaart 1:200 000** (`AP200`)
ja **Pinnakatte kaart 1:200 000** (`Q200`). Aluspõhjakaart sisaldab avamusi,
rikkeid, astanguid ja stratotüüpe; pinnakattekaart ühendab geneesi ja litoloogia.
Mõlemat saab Kihid-paanil sisse/välja lülitada ning nupureale tõsta.

Läbilõigete tööriistas piisab nüüd kaardile joone joonistamisest: nähtavad EGT,
Portali Faktika ja välikaardistamise punktid, VEKA ning SARV puursüdamikud, mis
jäävad joonest kuni 100 m kaugusele, lisatakse automaatselt. EGT, Portali ja
VEKA geoloogilised intervallid laaditakse pärast joone kuvamist taustal ning
juba nimekirjas olevad objektid topelt ei lisandu.

**Kihid → Kaardisildid** võimaldab muuta Qeoloogi EGT puuraukude ja
vaatluspunktide, SARV kohtade ning VEKA puurkaevude siltide teksti suurust
vahemikus 1–72 pt. Muudatus rakendub avatud kihtidele kohe, salvestub QGIS-i
kasutajaprofiili ja säilib programmi taaskäivitamisel. Vaikesuurus on 5 pt;
0,6 mm valge sildipuhver jääb muutmata.
EGT puuraukudele (PA) ja vaatluspunktidele (VP) saab samas plokis eraldi
linnukestega valida ühe või mitu sildirida: nimi, alias, sügavus, pinnakatte paksus,
aluspõhja reljeefi absoluutkõrgus, 0,5 m sügavuse indeks koos geneesi ja
litoloogiaga ning AP avamus ehk esimene aluspõhja indeks. Mitme valiku korral
kuvatakse väärtused samas sildis loetavate eraldi ridadena. Vaikimisi näitab
PA nime ja VP 0,5 m kirjeldust, nagu varasemates versioonides. Tuletatud
väärtused arvutatakse esimese aluspõhjaintervalli järgi ning laaditakse
asünkroonselt ainult nähtava kaardiulatuse objektidele.
Kui aluspõhja pealispind on maapinnast vähem kui 1 m sügavusel, kasutab
`0,5 m` sildirida alati esimese aluspõhjaüksuse indeksit ja litoloogiat, mitte
õhukese pinnakatte kirjeldust.
Samad PA/VP sildireeglid rakenduvad ka autentitud Faktika töökihtidele ja
välikaardistamise punktidele. Portali kirjeldusi küsitakse kuni 120 nähtava
objekti kaupa ja tulemused puhverdatakse, mistõttu ei laadita kaardiliigutusel
kogu sisemist andmestikku.
Alias kuvatakse ilma eesliiteta. Tuletatud read kasutavad lühitähiseid `PP`
(pinnakatte paksus), `APR` (aluspõhja reljeefi absoluutkõrgus), `0,5 m` ja
`AP` (esimene aluspõhja indeks).
Kogu **Kihid** paan on vertikaalselt keritav, mistõttu ei suurenda pikk
kihikataloog ja seadistusvorm enam QGIS-i akna minimaalset kõrgust ega jää
väiksemal ekraanil aknast välja.
**Otsing ja filtrid**, **VEKA** ning **Ekspordi**
paanides ei muuda hiireratas suletud rippmenüü väärtust. Rippmenüü sisu saab
kerida pärast selle avamist; suletud menüü kohal kerides liigub paan ise.

Maardlate piirid, aktiivsed mäeeraldised ja aktiivsed uuringualad kasutavad
Layers-paanis ühist maavara liikide värvipaletti. Kihi legendist saab liike
eraldi sisse ja välja lülitada. Qeoloogi kaardiklõps avab nende objektide
registriandmed **Objekti andmed** paanis; kattuvate polygonide korral
eelistatakse parajasti aktiivset kihti. Aktiivsed uuringualad kuvatakse
maavara liigi värvi täiteta piirjoonena.

Ka **Ehitusgeoloogilised uuringupunktid** on Qeoloogi objektidena avatavad.
Üldandmetes kuvatakse geoloogiafondi aruande kirjeldus, osalised, uuringuliik,
maksimaalne sügavus, juurdepääsupiirangud ja muud WFS-is avaldatud väljad.
EGF-i tunnus ja aruande püsilink avavad vastava kirje geoloogiafondis.

Otsingupaani **Maavarade register** ja **Geoloogiafond** allikad otsivad
maardlaid, aktiivseid mäeeraldisi, aktiivseid uuringualasid ning
Geoloogiafondi uuringualasid nime või registri ID järgi otse WFS-teenusest.
Geoloogiafondi tulemuse avamisel lisatakse projekti ainult valitud `egf_id`
serverifiltriga uuringuala ning see kuvatakse täiteta piirjoonena. Abikihtide
hulgas on Maa- ja Ruumiameti ametlik **Kaardilehed 1:50 000** (`KV`,
`epk_50T`). Kaardilehtede ruudud jäävad suumimisel samaks. Varasem kohanduv
KV võrk asendatakse ka salvestatud seadistustes ja avatud Qeoloogi kihil.

## English

## Layer catalogue and MaRu drill cores

The **Layer catalogue** on the **Layers** page searches every configured
layer by code, name, service layer or URL and can filter the list by protocol,
home group and enabled state.

The default **MP – MaRu historical drill-core database** entry downloads the
official public ZIP export of the Estonian Land and Spatial Development Board
and builds a read-only SQLite search index in the user's QGIS profile. The
source data is not bundled with the plugin. It can be refreshed explicitly on
the Layers page. MP records can be mapped, searched, opened and included in a
combined cross-section.

An EGT borehole's `ma_orig_id` links to the MaRu `pa.id`. When that official
ID is missing, an automatic match is confirmed only when the number,
descriptive name and location within 500 metres agree. This safely links MaRu
1498 **735 Mustvee**, EGT GEA 194350 and SARV locality 23365 while rejecting a
distant borehole with the same number.

The combined object view adds MaRu general data, geological intervals, core
boxes and their images, samples and sample images. EGT remains the primary
geological-log source; MaRu fills only depth gaps not covered by EGT. Separate
header switches enable or disable the EGT and MaRu logs, core boxes and
samples. Gap-fill intervals are labelled with their source. When more than
one source has core boxes, the profile draws adjacent source lanes over the
lithology column: **K** for EGT, **S** for SARV and **M** for MaRu. Missing
box coverage is hatched independently in each lane.
**MaRu link management** can add or replace the MaRu ID, mark the original
source link invalid, and restore it later. Overrides are validated against the
local official export, stored only in the QGIS user profile and never written
to either source system. **Export SARV and MaRu links** writes all local link
corrections and invalid-source markers to CSV or JSON.

The MaRu-to-EGT link is also resolved directly against the public EGT WFS, so
it remains available when the public borehole/observation layers are not
loaded. MaRu map points use the same cover, bedrock, basement and unknown
categories as EGT points. MaRu sample images are clickable in the profile,
and a sample's location reference is searchable and links back to its MaRu
collar. The source-grouped
**Attachments** table shows their depth, source-derived absolute elevation,
index, lithology and complete source metadata. Old MaRu elevations are not
silently labelled EH2000 when the datum is unknown. Core-box images remain in
the **Drill core** tab by default and can optionally also be shown under
Attachments.

**Search and filters** combines Search, EGS, SARV and MaRu views in one tab;
VEKA remains separate. MaRu filters cover identifiers, archive fund, rock,
storage, box, collector, year, EGS/SARV links, image availability and sample
processing flags. Selected search results can be added directly to a combined
cross-section.

A negative MaRu geological `D` value identifies the terminal unit whose lower
boundary was not penetrated. Qeoloog uses `abs(D)` as its displayed thickness
and adds `+` to the index. Reversed invalid box depths are not drawn as
inverted intervals; the original value remains available in the detailed view
for a local correction. MaRu free-text search covers overview data as well as
geological descriptions, core boxes and samples.

## Read-only detailed view

The **Detailed view** button in the selected object's **Object data** header
opens a separate large window. **Overview** lists only populated fields and,
where applicable, shows the decoded label beside the original source code,
technical field name and data source. Every non-empty related dataset—core
boxes, samples, analyses, specimens, attachments, literature and VEKA
construction, pumping tests and water chemistry—gets its own table.

Users can search the active table, open links by double-clicking, and copy
selected rows, the active table or the complete view to the clipboard as TSV.
`Ctrl+C` (`Command+C` on macOS) copies selected rows, or the active table when
nothing is selected. Double-clicking a related-data row opens all populated
source fields for that record; double-clicking a link cell opens the link.
The window has no edit or save operation and works for public, VEKA, SARV and
authenticated EGS Portal objects alike.

## EGS ArcGIS Portal (read-only)

Qeoloog can add public and authenticated ArcGIS FeatureServer layers for
viewing only. Authentication remains in QGIS'
encrypted authentication database; Qeoloog's settings retain only the
selected `authcfg` identifier and never store a username, password or OAuth
token.

Every Portal layer opened through Qeoloog is marked read-only in QGIS. Object
creation, editing, deletion and fieldwork-upload controls are not shown, and
all former Portal write paths are blocked both at application and network
request level. Sign-in, the catalog, map layers, server legends, object data,
attachments, labels and cross-sections remain available.

1. Open **Qeoloog → Layers → EGS Portal** and select
   **Connect to EGS Portal**.
2. On first use, enter the **Client ID** and **Client secret** from the
   organisation's internal guide. Qeoloog fills in the Authorization Code
   flow, request and token endpoints, redirect and `X-Esri-Authorization`
   header, then saves the configuration in QGIS' authentication store. This
   setup dialog is not shown on subsequent connections.
3. Complete the normal EGS Portal sign-in in the browser. Qeoloog displays
   the active account and automatically reads every Feature Service visible
   to it.
4. An **EGT** menu appears beside **LK** on the toolbar. Services are grouped
   by access (**Shared with me**, **Organisation**, **Public**) and then by
   their ArcGIS REST service folder.
5. Open a service and tick one or more sublayers. Sublayers are requested only
   when their service menu is opened, keeping even a large catalog responsive.
   Clear a tick to remove that layer from the project.

Qeoloog never initiates OAuth during QGIS startup. The browser sign-in opens
only after the user explicitly connects or refreshes the Portal catalog, so a
slow or unavailable Portal cannot block QGIS from opening.

Portal layers automatically receive the authoritative EGS legend published in
the FeatureServer. This preserves stratigraphic colours, fault line styles,
category labels and published point markers. If QGIS cannot convert an unusual
ArcGIS symbol, the native AFS provider's server style remains in place.

Selecting an existing authentication configuration and opening the complete
QGIS authentication settings remain available under **Advanced settings**.
Manual FeatureServer URL entry remains available for custom services or items
which are not present in the catalog.

The same collapsed section contains **Show the Faktika test server in the EGT
menu**, disabled by default. Enabling it adds a separate orange warning entry
for the fixed `testgis.egt.ee` FeatureServer. It uses the selected QGIS
authentication configuration and loads its point layer and related tables
read-only in a separate group, retaining live REST domains, labels, object
details and cross-section support. Layer and table IDs are discovered from
the test service metadata instead of assuming production numbering.

### Archived editing design

Since version 3.37.0, the Portal editing workflows documented below are
disabled and their controls are absent from the application. They are retained
only as a technical archive for a future separately approved solution; the
active plugin sends no changes to Portal.
The retained technical specification is in
[`docs/PORTAL_EDITING_ARCHIVE.md`](docs/PORTAL_EDITING_ARCHIVE.md).

QGIS previously loaded the result using its native ArcGIS FeatureServer provider. When the
signed-in account and service allow `Create`, `Update` or `Delete`, Qeoloog
shows permission-aware controls for starting an edit session, committing it to
Portal or discarding it. Standard QGIS tools edit geometries and attributes.
Editing controls remain hidden for a read-only account. No Portal client secret
or token is included in the plugin package.

Signed-in users also see **Fieldwork import → Geophysical fieldwork** in the
same panel. It reads the required `x`, `y` and `z` CSV columns in file order and
creates one Z-enabled multipart line in the Portal layer, starting a new part
where consecutive points are more than 50 metres apart. EPSG:3301 is the
default input CRS and can be changed before upload. Name, date, method, device,
responsible person and notes are collected before saving. Method, device and
responsible-person choices are read from the live Portal coded-value domains,
and nothing is sent until **Upload to Portal** is pressed.
The layer legend is always categorized by `geofys_meetod` (**Method**). Qeoloog
restores this rule when a project is opened and after Portal edits are saved or
discarded, as well as after a CSV upload.

The signed-in **EGT** menu highlights **Faktika working layer**. It loads the
internal PointZ object layer together with the Person, Attachment keyword,
Attachment, Access basis and Geological unit tables under one dedicated group.
The point legend is nested by object type (borehole, observation point or
offshore observation point) and geological category (cover, bedrock, basement
or other/unknown). Public PA/VP layers are temporarily hidden to prevent
duplicate rendering and their previous visibility is restored when Faktika is
closed.

Signed-in users get **Add object** and, after a safe record match, **Edit** in
Object data. Public and internal records are matched by exact GlobalID first;
`gea_id` is only a checked fallback, and a GlobalID disagreement is reported
as a conflict rather than opening the wrong record. The separate resizable
editor covers PointZ X/Y/Z coordinates, metadata, geological intervals,
attachments and keywords, and access bases. Interval thickness and absolute
Z1/Z2 values are derived automatically, while object length follows the last
geological interval. Formation choices are limited to the selected index;
genesis is editable only for cover and lithology supplements only for bedrock.
For a compound unit, the ordinary formation is replaced by upper and lower
index controls and their corresponding formations. A new interval inherits
the preceding interval's unit type, author, source basis and source number.
Invalid Portal template code `0` is replaced with **Unknown**, while formation
codes `997` and `998` are displayed as **Unknown** and **Not applicable**.
Cover cannot follow bedrock or basement, and bedrock cannot follow basement.
Date fields, including completion time, use a readable calendar and time
editor.
Required values, live coded
domains, increasing and non-overlapping depths, total depth, cover genesis and
compound-unit ordering are validated before save. Parent and related edits are
sent as one rollback-enabled Portal transaction, with an optimistic timestamp
check to avoid overwriting a record changed by another user.
Qeoloog deliberately excludes creator/editor names and creation/edit dates
from its edit payloads. ArcGIS FeatureServer editor tracking assigns these
audit fields from the signed-in account and server time when tracking is
enabled on the service.

When adding an object, its PointZ location can be picked directly on the map
or initialized at the map centre. The parent geological-category code is
derived from its units in the order basement, bedrock, cover, then other /
unknown, and detail views show the corresponding labels instead of numeric
codes. The drill-core tab also supports local-only addition and editing of
core boxes, depth extents, diameter, status and descriptions; these corrections
are included in the local correction export and never modify EGT or SARV data.
EGT box statuses are refreshed from the live coded-value domains in AUQ REST
table 22 whenever an editor is opened and shown by their authoritative label;
SARV storage choices come from the active object's API data. Any edited depth
interval is checked against every box from the same source. If intervals
overlap by a positive depth, the user can edit the conflicting box as part of
the same operation or cancel. Nothing is persisted until the affected set is
conflict-free; touching boundaries remain valid.

The EGT menu also promotes **EGT korrastatavad puuraugud v2** and **Faktika
välikaardistamine** as complete related bundles. The cleanup dataset uses the
same Object data editor across its object and five related tables. Field
mapping loads its point and description table together and uses QGIS's native
permission-aware Portal editing controls. Portal image attachments are listed
in Qeoloog's **Attachments** tab and opened through an authenticated local
download.

Authenticated Faktika and field-mapping points use the same configurable EGT
label-content rules as public boreholes and observation points. Derived label
values are fetched in bounded batches for visible features only. These Portal
points also participate in cross-section snapping and background interval
loading.

When an edited borehole has no SARV relation, the editor offers its locally
confirmed match or up to five plausible candidates. A confirmed local match is
preselected, while a new candidate is applied only after explicit selection
and save. The choice is stored in Qeoloog's local match registry and does not
silently overwrite the Portal `sarv_id` field.

The SARV match selector is placed compactly beside the Portal **SARV ID**
value. **Elevation-based location check** is a collapsed expandable section by
default. **Depth**, **Depth method** and **Underwater depth** are shown only for
offshore observation points. Four separate compound-unit columns are reduced
to **Upper compound unit** and **Lower compound unit**, each combining its
index and corresponding formation. Index-filtered formation choices always
retain readable **Unknown** (`997`) and **Not applicable** (`998`) entries.
The Portal schema publishes no contingent relationship between lithology and
lithology supplements, so Qeoloog does not impose a speculative hard filter.
**Notes** and **Additional information** are placed in the right-hand details
form and use multiline text areas, with extra room reserved for Notes.

The Portal editor's **Elevation-based location check** compares a legacy
report elevation—often more reliable than its XY—with a selected file-based
DEM. The user explicitly selects the object and raster height datums and a
tolerance. **Show matching area** adds a temporary green/yellow raster directly
below the active Faktika point layer and makes pixels outside `Z ± tolerance`
transparent. Picking a candidate on the map reports the DEM's robust 3×3 pixel
median and range, elevation delta and distance from the original position.
**Use candidate X/Y** copies only the candidate coordinates into the editor;
it never replaces Z with a DEM value and nothing is sent to Portal until the
normal full-object save.

Object heights can be declared as EH2000, BK77, EUREF-EST97 ellipsoidal or
unknown. BK77↔EH2000 and ellipsoidal↔EH2000 conversions use the official
coordinate-dependent MaRu model services. Unknown datums remain unconverted
and visibly flagged. Single-band DEMs automatically use band 1; the elevation
band selector is shown only in advanced settings for multiband rasters, and
the choice is remembered per raster. This workflow is available only inside
the signed-in EGT Portal editor.

**Additional layers → Helpers → Utility infrastructure restriction zones**
(`TV`) combines telecommunications, electricity, gas, district heating and
water-supply restriction zones in one WMS layer from the public MaRu KPOIS
service. It can be enabled, disabled or moved to the toolbar in the Layers
panel. The layer shows restriction zones, not precise utility route lines.

**Additional layers → Geology** includes the EGT **Bedrock map 1:200,000**
(`AP200`) and **Quaternary map 1:200,000** (`Q200`). The bedrock map combines
outcrops, faults, escarpments and stratotypes; the Quaternary map combines
genesis and lithology. Both can be enabled, disabled or moved to the toolbar
in the Layers panel.

Qeoloog is a QGIS 4 application focused on viewing, linking and exploring
geological data from the Geological Survey of Estonia (EGT) GEA database and
the SARV geoscience data platform, as well as EELIS/VEKA water-well data. It
provides an interactive view of
boreholes and observation points, including geological logs, drill-core boxes
and images, samples, analyses, specimens, attachments and literature.

The plugin also provides configurable access to WMS and WFS services from the
Estonian Land and Spatial Development Board (MaRu) and other public data
providers. The user interface can be displayed in Estonian or English.
**Additional layers → Geology → GTK** contains official public Geological
Survey of Finland WMS/WFS layers in their native EPSG:3067 request CRS. The
Qeoloog **i** tool opens attributes from GTK WFS features and GetFeatureInfo
attributes from queryable GTK WMS maps in the copyable detail view. GTK WMS
legend graphics use a white background for readability in dark QGIS themes,
while the map overlays remain transparent.
**Additional layers → Geology → Latvia** contains official public LVĢMC and
GeoLatvija bedrock and Quaternary maps, geological boreholes, karst areas,
faults, seismic profiles, groundwater bodies, mineral deposits, extraction
licences and extraction limits. Latvia boreholes can be searched from the
shared **Search and filters** view using the **Latvia LVĢMC** source. The
Qeoloog **i** tool opens available vector attributes and queryable WMS
GetFeatureInfo results in the copyable detail view. The public borehole layer
currently exposes 181 points with identifiers/names, year, coordinates and
purpose, but it does not publish geological logs or drill-core images; Qeoloog
therefore shows only the authoritative fields returned by the service.
Mineral-deposit boundaries, active mining claims and active exploration areas
are grouped by mineral-resource type in the QGIS Layers legend. Clicking one
of these polygons opens its available register attributes in Qeoloog; the
currently active layer takes precedence where polygons overlap. Active
exploration areas use resource-coloured outlines without polygon fill.
**Engineering geology survey points** also support click-to-open details,
including report metadata, participants, survey type, maximum depth, access
restrictions and a direct permanent link to the Geological Archive.
The Search tab can query mineral deposits, active mining claims, active
exploration areas and Geological Archive survey areas by name or registry ID
directly from their WFS services. Opening a Geological Archive result adds
only that report's server-filtered `egf_id` geometry and renders it as an
unfilled outline. Reference layers include the official **Map sheets
1:50,000** (`KV`, `epk_50T`), whose cells remain fixed when zooming. Saved
built-in KV settings and loaded Qeoloog grid layers are migrated from the
previous adaptive coordinate grid.
Validated EGT–SARV link corrections can associate an EGT object with a SARV
drill core, locality or research site. They are stored locally, applied
immediately to the combined detail view, restored to the original GEA link and
exported together as CSV or JSON.
When drawing a multi-well section, visible EGT, VEKA and SARV drill-core points
within a 100 m corridor are added automatically; EGT and VEKA intervals are
then loaded asynchronously without duplicating objects already in the section.
The geological profile draws subtle boundary guides from each boundary-depth
label towards the lithology column. Hidden P, A, SP, SA and SE tracks are also
removed from the horizontal layout so the profile becomes more compact.
For EGT observation points, genesis is shown beside the stratigraphic index
(for example `Q1jr3 · lg`). Their default map label shows the index, genesis
and lithology at **0.5 m** (for example `Q1jr3 · lg · Peenliiv`), using the
original EGT terminology.
At a shared boundary the deeper interval is used; a terminal bottom at 0.5 m
is also accepted. Missing depth coverage produces no label. Conflicting
overlapping descriptions are separated by `/`, without mixing their values.
Labels use 5 pt text with a 0.6 mm white buffer. Compact WFS lookups are loaded
in the background only for points in the visible map extent and reused; map
redraws do not make per-point HTTP requests. Labels are retained with the QGIS
project while fresh data loads.
The **Layers → Map labels** setting changes the label text size for EGT
boreholes and observation points, SARV locations and VEKA water wells from
1 to 72 pt. It updates loaded layers immediately, persists in the QGIS user
profile, and defaults to 5 pt. The 0.6 mm white buffer remains unchanged.
Separate PA and VP checkbox columns can combine name, alias, depth, Quaternary-cover
thickness, bedrock-surface elevation, the 0.5 m index/lithology description,
and the first bedrock index in one multi-line label. PA defaults to Name and VP
to the 0.5 m description. Cover thickness, bedrock-surface elevation and the
outcrop/subcrop index are all derived consistently from the shallowest valid
bedrock interval.
If the bedrock surface is shallower than 1 m, the 0.5 m label deliberately
uses the first bedrock unit instead of a very thin cover interval.
Aliases are shown without a prefix. Derived rows use the compact prefixes
`PP`, `APR`, `0.5 m` and `AP`.
The complete **Layers** page is vertically scrollable, so the layer catalog
and service form no longer force the QGIS window beyond the available screen
height.
On the **EGT filters**, **SARV filters**, **VEKA**, **Search** and **Export**
pages, the mouse wheel cannot change a closed selector. Its options remain
scrollable after the selector is opened; otherwise the wheel scrolls the page.
SP, SA and SE tracks and their controls are hidden for observation points;
switching back to a borehole restores the previous checkbox preferences.
Sample, analysis and specimen switches are also omitted from the profile
header whenever the current object has no corresponding EGT or SARV records.
An optional **Apply filters** control filters profile markers with the active
EGT and SARV sample, analysis and specimen-type filters. EGT map filters also
include the complete official stratigraphic-index list and a partial
**Contains** query across ordinary and compound indices.
**Show combined selected-unit thickness** keeps the original borehole name on
the first line and adds one combined thickness for all selected units below
it. A source interval matching several selected parent/child indices is
counted only once, and index codes are not printed on the map. Thickness
represented only by a compound-unit interval is kept separate in parentheses.
A trailing `+` indicates that a selected unit reaches the bottom of the
borehole and was therefore not drilled through.

The compact **Cross-sections** tab opens or hides a separate resizable
cross-section window. It combines selected EGT boreholes and observation
points, SARV drill cores and VEKA water wells on shared absolute-elevation and
distance axes without forcing the main Qeoloog dock to become wider. A section
can follow a line drawn on the map, the object order, or equal spacing.
**Draw on map** automatically enables QGIS snapping. While drawing the map
line, vertices snap within 12 screen pixels to visible
EGT boreholes and observation points, SARV drill cores and VEKA water wells.
A yellow square previews the exact snap location. The snapping index is
rebuilt after filters, layer visibility or source data change. Finishing,
cancelling or leaving the drawing tool restores the previous QGIS snapping
configuration.
The object table is placed below the drawing, can be collapsed, and follows
the same chainage order as the displayed columns when the section follows a
map line. Its open/closed state is saved with the QGIS project.
Geological units, drill-core boxes, samples, analyses, specimens, VEKA
construction and static water levels can be switched independently. A loaded
local DEM raster can be sampled along the section line and compared visually
with recorded wellhead elevations. The result is stored in the QGIS project
and can be exported to SVG or PDF with an optional overview map.
Over the drawing, `Ctrl`/`Command` + mouse wheel changes the vertical scale
and `Shift` + mouse wheel or horizontal touchpad/wheel gestures change the
horizontal scale. Pixel-only trackpads are supported. Manual horizontal zoom
overrides initial automatic spacing. Both values remain in sync with the scale
controls and are persisted in the project.

The **Export** tab selects an area by drawing a polygon on the map or opening
a polygon vector file. Loaded EGT, SARV and VEKA points inside the area can be
written as Leapfrog-compatible `collar.csv`, `survey.csv` and `interval.csv`
tables. VEKA exports can optionally include static water level, specific
capacity and one or more selected normalized water-analysis results.

The drill-core **Editing mode** stores local EGT and SARV box corrections on
the user's computer without modifying either upstream database. Corrected
depths and other box fields are used in tables and cross-sections, and all
saved corrections can be exported as JSON or CSV from the **Export** tab.

## Koondläbilõiked

EGT puuraugu või vaatluspunkti, SARV puursüdamiku ja VEKA puurkaevu saab lisada
objektivaate päise linnukesega **Lisa läbilõikele**. Qeoloogi põhidoki
**Läbilõiked** paan on kompaktne: **Ava läbilõikeaken** avab kogu tööala eraldi
muudetava suurusega aknas ja sama nupp peidab selle taas. Akna sulgemisrist ei
kustuta läbilõiget. Eraldi aknas saab:

- paigutada objektid kaardile joonistatud läbilõikejoone, kasutaja määratud
  järjekorra või võrdsete vahede järgi;
- nupuga **Joonista kaardil** automaatselt snapi sisse lülitada ning snäppida
  joone tipud 12 ekraanipiksli ulatuses nähtavate EGT
  puuraukude ja vaatluspunktide, SARV puursüdamike ning VEKA puurkaevude
  täpsetele asukohtadele; snäpikohta näitab kollane ruut. Indeks uueneb
  filtrite, kihtide nähtavuse või andmete muutumisel. Joonistamise lõpetamisel,
  tühistamisel või teisele tööriistale minnes taastuvad varasemad snäpiseaded;
- muuta objektide järjekorda, pöörata läbilõige ümber, objekt eemaldada või
  puuduva/ebatäpse absoluutkõrguse käsitsi määrata;
- kasutada joonise all kokkupandavat objektiloendit, mis on kaardijoone režiimis
  samas piketijärjekorras nagu läbilõikel kuvatavad tulbad;
- kuvada tulbad ühisel absoluutkõrguse skaalal ning tegeliku piketi ja
  läbilõikejoonest kõrvalekaldega;
- lülitada eraldi indekseid, litoloogiat, piire, puursüdamikukaste, proove,
  analüüse, eksemplare, VEKA konstruktsiooni, staatilist veetaset ja suudmeid;
- hoida läbilõikejoont kaardil nähtavana;
- eksportida SVG- või A3 PDF-faili, soovi korral koos QGIS-i kaardi
  ülevaateaknaga.

Läbilõike olek salvestub QGIS-i projekti. Horisontaalset ja vertikaalset
mõõtkava saab muuta paanil olevatest väljadest; joonise kohal muudab
`Ctrl`/`Command` + kerimisratas vertikaalset ning `Shift` + kerimisratas või
horisontaalne puuteplaadi liigutus horisontaalset mõõtkava. Käsitsi valitud
horisontaalne mõõtkava jääb kehtima ka joonise värskendamisel.

### DEM-i võrdlus

**DEM** rühmas kuvatakse projektis avatud failipõhised rasterkihid (WMS
aluskaarte DEM-ina ei pakuta). Pärast rasterkihi ja kõrguskanali valimist loeb
**Loe DEM-profiil** maapinnakõrguse piki läbilõikejoont. Salvestatud
absoluutkõrgust ei kirjutata DEM-i väärtusega üle:

- roheline joon näitab DEM-i maapinda ja pruun joon andmetes olevaid suudmeid;
- iga objekti juures kuvatakse `ΔDEM` ning kahe kõrguse vahe mõõtejoon;
- alla 1 m erinevus on roheline, 1–3 m erinevus merevaigukollane ja vähemalt
  3 m erinevus punane;
- kaardijoonest eemal oleva objekti puhul kuvatakse ka kõrvalekalle, sest
  `ΔDEM` võrreldakse objekti projektsiooniga läbilõikejoonel.

Nii jääb lähteandme kõrgus auditeeritavaks, kuid võimalik vale
absoluutkõrgus on joonisel kohe nähtav.

## Kohalikud andmeparandused

Objektivaate **Puursüdamik** paanis saab aktiveerida
**Redigeerimisrežiimi**, valida EGT või SARV puursüdamiku kasti ja muuta:

- kasti numbrit;
- ülemist ja alumist sügavust;
- diameetrit;
- staatust või hoiukoha kirjeldust.

Muudatused salvestuvad QGIS-i kasutajaprofiili ainult kohalikus arvutis.
EGT ega SARV algandmebaasi ei kirjutata. Parandatud väärtusi kasutatakse
puursüdamiku tabelis ja läbilõikejoonistel; veerg **Muudetud** näitab kohaliku
paranduse aega. Nupuga **Taasta algandmed** saab valitud kasti paranduse
eemaldada.

**Ekspordi** paani rühmas **Kohalikud andmeparandused** saab kõik salvestatud
puursüdamiku kastide parandused eksportida:

- JSON-failina koos algväärtuste, parandatud väljade, lähte-ID-de ja
  ajatemplitega;
- CSV-failina, kus iga muudetud väli on eraldi auditireana.

## Leapfrog-eksport

**Ekspordi** paanis saab valida ala kahel viisil:

- joonistada QGIS-i kaardile vabakujuline polygon;
- avada polygonkiht GeoPackage-, Shapefile-, GeoJSON- või KML-failist.

Ekspordiks tuleb vastavad PA/VP, SK ja/või VK kihid esmalt projekti laadida.
Valida saab EGT, SARV ja VEKA eraldi või mistahes kombinatsioonis. Kihile
rakendatud aktiivne QGIS-i filter jääb ekspordil kehtima. Väljundi
koordinaatsüsteem on seadistatav; vaikimisi kasutatakse `EPSG:3301`.

Valitud kausta luuakse:

- `collar.csv` – Hole ID, X/Y/Z, kogusügavus, allikas, lähte-ID ja nimi;
- `survey.csv` – Hole ID, mõõtesügavus, asimuut ja kalle;
- `interval.csv` – From/To, litoloogia, stratigraafia, allikas ja
  intervallitüüp;
- `export_report.txt` – CRS, ridade arv, puuduva absoluutkõrgusega objektid
  ning päringute hoiatused.

EGT Interval-ridades eksporditakse nii litoloogia kui indeks. Kui indeks on
`Liitüksus`, kirjutatakse väärtus kujul `alumine-ülemine`, näiteks
`O3mo-O3adl`. VEKA Interval-ridades kasutatakse puurkaevu geoloogilist
läbilõiget. SARV puursüdamike kastid eksporditakse `DrillcoreBox`
intervallidena koos olemasoleva stratigraafia ja kastikirjeldusega.

VEKA puhul saab Collar-tabelisse lisada:

- uusima olemasoleva staatilise veetaseme sügavuse ja absoluutkõrguse;
- uusima arvutatava eritootlikkuse ühikus l/(s·m);
- ühe või mitu veeanalüüsi näitajat. Ühildatavad lähteühikud teisendatakse
  Qeoloogi ühtlustatud ühikusse ning mitme tulemuse korral saab kasutada
  uusimat, suurimat, väikseimat või keskmist väärtust.

Kui kalde või asimuudi info puudub, lisatakse Survey-tabelisse vertikaalselt
alla suunatud trajektoor `Dip = +90°`, `Azimuth = 0°`. See vastab Leapfrogi
vaikeseadele, kus negatiivne kalle näitab üles. Puuduvat absoluutkõrgust ei
asendata nulli ega oletatava väärtusega; objekt jääb Collar-tabelisse tühja
Elevation-väljaga ja märgitakse ekspordiaruandes.

## Tööriistariba

Vaikimisi on ribal seitse otsenuppu:

| Nupp | Kiht | Teenus |
|---|---|---|
| PK | põhikaart reljeefivarjutusega | WMS |
| OF | ortofoto | WMS |
| HK | hübriidkaart | WMS |
| PA | EGT puuraugud | WFS |
| VP | EGT vaatluspunktid | WFS |
| SK | SARV lokaliteedid, uuringupunktid ja puursüdamikud | SARV API |
| AP | EGT 1:50 000 aluspõhja avamused | WMS |

**LK** avab lisakihtide menüü. Seal on muu hulgas **VK** ehk EELIS/VEKA
puurkaevud ning aluskaardid, geoloogia, uuringute ja
maavarade kihid ning abikihid, muu hulgas kitsenduste vööndid. Menüü linnuke
lisab või eemaldab kihi.
Kui LK-menüüst lisatud kiht on projektis aktiivne, ilmub selle nupp ajutiselt
otse tööriistaribale. Ajutise nupu vajutamine eemaldab kihi ja nupp kaob; kihi
püsiv asukoht jääb endiselt tema kodurippmenüüsse.

## Seadistamine

Hammasratta alt saab:

- valida kogu kasutajaliidese eesti või inglise keele;
- valida EGT läbilõike detailandmete esmaseks allikaks WFS-i või GEA API;
- näidata või peita LK rippmenüüde rühmi;
- paigutada iga kihi põhiribale, tema kindlasse kodurippmenüüsse või keelata;
- lisada ja eemaldada WMS/WFS kihte ning SARV ja VEKA punktikatalooge;
- lugeda GetCapabilities-kihiloendi;
- muuta tähist, värvi, nime, URL-i, kihinime ja WMS-stiili;
- lülitada sisse režiimi, kus otsenupu korduv vajutus eemaldab kihi;
- eksportida kõik kohalikud EGT–SARV seoseparandused CSV- või JSON-failina;
- taastada Qeoloogi vaikekataloogi.

Kihi kodurühm on pärast loomist lukus: näiteks katastriüksuseid ei saa tõsta
geoloogia rühma. Seadistus säilib QGIS-i kasutajaprofiilis.

## VEKA puurkaevud

**VK** laadib EELIS-e avalikust API-st VEKA puurkaevud lokaalsesse QGIS-i
punktikihti. Põhiandmed laaditakse ühe korra ning mahukamad seotud tabelid
alles siis, kui vastavat filtrit või kujundust kasutatakse. Veeanalüüside puhul
laaditakse eraldi näitajate kataloog ja seejärel ainult valitud näitaja
tulemused. Sama näitaja teisendatavad ühikud ühendatakse: massikontsentratsioon
teisendatakse ühikusse mg/l, elektrijuhtivus ühikusse µS/cm ning
mikrobioloogilised arvud ühikusse arv/100 ml. Näiteks Baariumi mg/l ja µg/l
tulemused on üks otsitav näitaja. Teadaolevad sama näitaja alternatiivsed
koodid ühendatakse samuti; ebaselge semantikaga koodid jäävad eraldi ning
nende kood kuvatakse valikus.

Deebiti väljad piiravad katsepumpamisel mõõdetud vooluhulka ühikus l/s.
Eritootlikkus arvutatakse sama katse deebiti ja veetaseme alanduse suhtena
ühikus l/(s·m). Valik **Mitme pumpamiskatse käsitlus** määrab, kas piisab ühest
sobivast katsest või kasutatakse uusimat, suurimat, väikseimat või keskmist
tulemust.

VEKA paanis saab puurkaeve filtreerida:

- nime, aadressi, registrikoodi, katastri-, passi- või seirenumbri järgi;
- otstarbe, kasutuse ja põhjaveekogumi mitmikvalikuga;
- puurimise aasta ja filtri sügavusintervalli järgi;
- pumpamiskatse deebiti ja arvutatud eritootlikkuse järgi;
- valitud veeproovi näitaja tulemuse ning proovivõtu aasta järgi.

Mitme pumpamiskatse või veeproovi korral saab kasutada vähemalt ühte vastet,
uusimat, suurimat, väikseimat või keskmist tulemust. Eritootlikkus arvutatakse
deebiti ja alanduse suhtena; puuduva või nullise alandusega katset ei kasutata.
VEKA aktiivsed filtrid rakenduvad ka ühisele otsingule. Kaardipunktilt saab
avada puurkaevu üldandmed, VEKA veebivaate ja olemasolu korral geoloogilise
läbilõike. Üldandmetesse lisatakse EELIS-est puurija nimi, registrikood,
puurimisviis, puurmasin või pärandandmetes säilinud ettevõtte kood, kui
vastav väärtus on olemas. VEKA objektil on EGT/SARV proovide, analüüside, eksemplaride,
manuste ja kirjanduse asemel eraldi **Konstruktsiooni**, **Pumpamiskatsete**
ning **Veekeemia** paanid. Konstruktsioonis eristatakse puuri diameetrit,
manteltoru, filtrit ja avatud või filtrita osa koos sügavusvahemike ning
diameetriga. Pumpamiskatsetes kuvatakse muu hulgas veetasemed, alandus,
deebit ja arvutatud eritootlikkus. Veekeemias ühendatakse uuema KOTKAS API
kirjed VEKA veebivaates säilinud pärandanalüüsidega, säilitatakse lähteühik
ning kuvatakse selle kõrval ka ühtlustatud tulemus. KOTKAS kirjel avab
**Protokoll** võimaluse korral originaalfaili ja muul juhul avaliku aruande;
pärandkirjel avab link VEKA lähtevaate.

Konstruktsioon kuvatakse ka VEKA läbilõikel eraldi sisselülitatava rajana.
Helehall täide tähistab puuri diameetrit, tume topeltjoon manteltoru, sinine
viirutus filtrit ning oranž katkendjoon avatud või filtrita osa. Raja laius
skaleerub konstruktsiooniosa diameetri järgi ja `Ø` märgis näitab diameetrit
millimeetrites. Uusim kuupäevaga staatilise veetaseme mõõtmine kuvatakse
eraldi sisse-välja lülitatava sinise joone, sügavuse ja mõõtmiskuupäevaga.
Veekeemia sidumisel normaliseeritakse katastrinumber ning
puuduva katastrinumbri korral tuletatakse võti võimalusel `PRK` registrikoodist.

VEKA sümboloogia disainer võimaldab määrata punkti värvi, suuruse või mõlemad
puurimise aasta, puuraugu või filtri sügavuse, deebiti, eritootlikkuse või
valitud veeproovi näitaja järgi. Kasutada saab kvantiile või võrdseid
vahemikke, 1–12 klassi, eri värviskaalasid ja seadistatavat markerisuurust.
Puuduvate väärtuste kuvamise saab halli klassina sisse või välja lülitada.
Valitud kujundus säilib QGIS-i kasutajaprofiilis.

### VEKA in English

The **VK** layer loads EELIS/VEKA water wells into a local QGIS point layer.
The VEKA tab filters wells by text, purpose, use value, groundwater body, drilling year,
filter-depth interval, pumping-test discharge, calculated specific capacity,
and a selected water-quality result and sampling year. Related tables are
loaded only when needed; water-quality metadata and the selected parameter's
results are requested separately. Convertible results for one parameter are
normalized to a common unit: mass concentration to mg/l, conductivity to
µS/cm, and microbiological counts to counts/100 ml. Known aliases such as the
alternative coliform and enterococci codes are combined, while ambiguous
codes remain separate and visible in the selector. The filtered wells are
also used by the shared Search tab. Discharge is entered in l/s; specific
capacity is calculated as discharge divided by drawdown in l/(s·m). The
multiple-test selector controls whether any, latest, maximum, minimum, or
mean pumping-test result is used.

Opening a VEKA map point uses a dedicated detail view. Instead of unrelated
EGT/SARV samples and analyses, it presents separate **Construction**,
**Pumping tests**, and **Water chemistry** tabs. The construction table
distinguishes bore diameter, casing, screen and open or unscreened intervals.
Pumping tests include water levels, drawdown, discharge and calculated
specific capacity; water chemistry retains the source value and unit next to
the normalized result. The water-chemistry table combines current KOTKAS API
records with analyses retained only in the legacy VEKA well page. Its protocol
link opens the original KOTKAS file where one is publicly available, otherwise
the public report or VEKA source page. Available driller, drilling method and
rig information is included in the overview. The newest dated static water
level is drawn on the VEKA profile as an optional blue line with its depth and
measurement date.

The shared Search tab can apply all matching EGT, SARV and VEKA objects as a
temporary map-layer filter without replacing the filters configured on the
source-specific tabs. Separate source choices search the Mineral Resources
Register and Geological Archive without requiring their complete polygon
layers to be loaded first. Reset clears the search criteria, result table and
the temporary point-layer filter.

The VEKA geological log also contains a separately switchable construction
track. Light grey represents bore diameter, double dark lines represent
casing, blue hatching represents a screen, and an orange dashed outline
represents an open or unscreened section. Track width is scaled by diameter
and the `Ø` label gives millimetres. Water-chemistry lookup normalizes the
cadastral number and can fall back to the `PRK` registry code.

The symbology designer maps colour, marker size, or both to drilling year,
well or filter depth, discharge, specific capacity, or the selected
water-quality parameter. It supports quantile and equal-interval classes,
configurable ramps and sizes, and an optional grey class for missing values.
The selected style is retained in the QGIS user profile.

Related-data tables for drill-core boxes, samples, analyses, specimens,
attachments and literature, as well as the VEKA-specific tables, can be
sorted in either direction by clicking a column header.

## EGT objektivaade

PA ja VP kihte saab filtreerida ulatuse järgi: pinnakate, aluspõhi, aluskord või
muu/teadmata ning selle järgi, kas objektil leidub puursüdamikku, proove,
analüüse või manuseid. Iga seotud-andmete filter toetab valikuid Kõik/Jah/Ei.
EGT proovide tüüpi, eesmärki ja staatust ning analüüside meetodit, laborit,
tulemuse tüüpi ja näitajat saab valida linnukestega mitmikvalikust. EGT
kõigi mitmikvalikute menüü jääb valimise ajal avatuks, sisaldab otsingut ja
skrollitavat loendit. Mõlemal filtrite paanil on kõigi tingimuste algseisu
taastamiseks nupp **Lähtesta**. EGT
koodinimetused loetakse automaatselt teenuse ametlikest ArcGIS-domeenidest ja
neid kasutatakse nii objektivaates kui filtrites. Sama välja valikud seotakse
OR-tingimusega, eri väljad AND-tingimusega; tühi valik tähendab kõiki.
EGT filtrites saab objekte piirata ka EGT 2023 stratigraafilise skeemi kõigi
indeksite mitmikvalikuga. Väli **Sisaldab** teeb osalise, tõstutundetu otsingu
tavaindeksi ning liitüksuse ülemise ja alumise indeksi seest. Mitmikvaliku ja
**Sisaldab** välja samaaegsel kasutamisel peavad mõlemad tingimused sobima.
Valik **Kuva valitud üksuste koondpaksus** jätab puuraugu algse nime sildi
esimesele reale ja lisab selle alla ühe kõigi valitud üksuste koondpaksuse.
Näiteks `D2nr` valik summeerib `D2nrV`, `D2nrK` ja `D2nrL` intervallid. Kui
valitud on korraga nii ülemindeks kui alamindeks, arvestatakse sama lähte-
intervalli ainult üks kord. Indeksite koode kaardisildile ei lisata.
Liitüksuse koosseisu kaudu leitud intervallide koondpaksus kuvatakse eraldi
sulgudes, sest sellest ei saa tuletada üksuse täpset osapaksust. Kui mõni
sobiv üksus ulatub puuraugu põhjani, lisatakse paksuse järele `+`, mis näitab,
et üksust ei ole täielikult läbitud.
Puuraukude nimed kuvatakse vaikimisi 5 pt sildina 0,6 mm valge puhvriga.
Vaatluspunktide silt näitab nime asemel **0,5 m sügavusel** oleva intervalli
indeksit, geneesi ja litoloogiat, näiteks `Q1jr3 · lg · Peenliiv`, sama
kirjasuuruse ja puhvriga.
Kahe kihi ühisel piiril kasutatakse sügavamat kihti; täpselt 0,5 m lõppeva
vaatluspunkti korral viimast kihti. Kui 0,5 m kohta andmed puuduvad, jääb silt
tühjaks. Kattuvate vastuoluliste kirjelduste korral kuvatakse need `/` abil
eraldatult, mitte kokku segatult. Sildiandmed laaditakse taustal WFS-ist
nähtava kaardiulatuse UUID-de kaupa ja neid kasutatakse mälust; kaardi
joonistamisel ei tehta iga punkti jaoks uut päringut. Projektiga salvestatud
sildid jäävad värskete andmete laadimise ajaks nähtavaks.
Vajuta **i**, seejärel klõpsa kaardil puuraugul või vaatluspunktis.
Hetkel avatavat punkti tähistab kaardil kerge halo. Objektivaade sisaldab:

- WFS-i üldatribuute; klikitavad on ainult `gea_id`, `kande_alus_nr` ning
  olemasolu või ühese vaste korral eraldi SARV-link;
- GEA `sarv_id` viitab alati SARV puursüdamikule; kinnitatud SARV lingi kõrval
  saab sama puursüdamiku avada otse Qeoloogi objektivaates;
- geoloogilist läbilõiget EGT 2023 stratigraafilise skeemi värvidega;
- indeksit, liitüksuse ülemist ja alumist indeksit ning litoloogiat;
- sisse-välja lülitatavaid geoloogiliste piiride sügavussilte;
- eraldi lülitatavaid EGT kastipiire, proove ja analüüse;
- eraldi SARV real lülitatavaid proove, analüüse ja eksemplare;
- proovide, analüüside ja eksemplaride lülitid ainult siis, kui aktiivsel
  objektil on vastava EGT või SARV allika kirjeid;
- valikut **Rakenda filtrid**, mis arvestab läbilõike P, A, SP, SA ja SE
  markeritel aktiivseid EGT ja SARV tüübi-, meetodi- ning tulemusefiltreid;
- kattuvate SARV markerite adaptiivset koondamist ja nelja horisontaalset rada;
- poolläbipaistvat viirutust sügavustel, kus puursüdamiku kast puudub;
- EGT ja SARV allika järgi lülitatavaid puursüdamiku kaste;
- EGT ja SARV kastidega seotud avatavaid fotosid;
- EGT ja SARV allika järgi lülitatavaid proove ning analüüse;
- klikitavaid SARV proove, analüüse ja eksemplare nii tabelites kui läbilõikel;
- analüüside sügavust või sügavusintervalli, kui lähteandmed seda sisaldavad;
- SARV kirjanduse eraldi paani pärast manuseid;
- EGT analüüsitulemusi ja manuseid.

Puursüdamiku kastil klõpsates avaneb selle foto; mitme foto korral saab valida
galeriimenüüst sobiva. SARV kastipiire saab läbilõikel eraldi sisse ja välja
lülitada ning need on EGT piiridest eristatud sinise punktiiriga. EGT ja SARV
kaste ei liideta automaatselt. SARV andmete sidumine kasutab avalikku SARV API-t
ning ainult üheselt tuvastatud leiukoha vastet. SK nupp laadib eraldi
punktikihtidena SARV lokaliteedid, uuringupunktid ja puursüdamikud.
Puursüdamik kuvatakse seotud lokaliteedi koordinaadil; koordinaadita kirjeid
kaardile ei lisata. Puursüdamiku punktilt saab avada valitud südamiku kastid,
pildid ning lokaliteediga seotud proovid, analüüsid, eksemplarid ja kirjanduse.
Neid kihte saab sama kaardiklõpsu tööriistaga avada nagu EGT punkte.

Ühise **Otsing ja filtrid** paani sisemises **SARV** vaates saab lülitada lokaliteete, uuringupunkte ja
puursüdamikke, piirata tulemust kaardiulatuse ja sügavusega ning valida
puursüdamiku, proovide, analüüside või eksemplaride olemasolu. Proovi eesmärk
ja tüüp, analüüsimeetod ning eksemplari tüüp on mitmikvalikud. Mahukad seotud
andmed päritakse SARV serverist alles filtri rakendamisel.

**Otsing ja filtrid** koondab **Otsing**, **EGT**, **SARV** ja **MaRu**
sisevaated ühte paani; eripärane VEKA otsing ja kujundus jääb eraldi.
Otsing leiab samast tabelist laaditud EGT puuraugud/vaatluspunktid, SARV
kohad ning kohalikust ametlikust indeksist MaRu puursüdamikud nime, numbri või ID,
kaardiulatuse, sügavuse ning proovi- või
analüüsitunnuste järgi. EGT objekte saab otsida ka EGT 2023
stratigraafilise skeemi indeksi järgi. Valitud indeksit võrreldakse tavavälja
ning liitüksuse ülemise ja alumise indeksiga; üldisema indeksi valik hõlmab ka
selle alamüksusi. Otsingus saab eraldi valida objektitüübid ning puursüdamiku,
proovide ja analüüside olemasolu. Tulemust saab nupust kaardil avada ja
objektivaatesse laadida ilma kaardi mõõtkava muutmata. Täpsed numbri- ja
ID-vasted ning nimevasted kuvatakse enne osalisi vasteid. Kuvatakse kuni 500
esimest vastet ning allikad ei liideta ilma kinnitatud vasteta üheks kirjeks.
**Rakenda filtrina** piirab otsingusse kaasatud kaardikihid leitud objektidega,
säilitades samal ajal EGT, SARV ja VEKA paanide muud aktiivsed filtrid.
**Rakenda läbilõikele** lisab tulemuste tabelis valitud toetatud punktobjektid
koondläbilõikele ning laadib nende profiilid taustal.
**Lähtesta** puhastab otsingutingimused, tulemused ja otsingufiltri.
MaRu sisevaates saab lisaks piirata otsingut MaRu ja GB ID, fondi, kivimi,
hoiukoha, kasti, koguja ning kogumisaasta järgi. Kõik/Jah/Ei valikud hõlmavad
EGT- ja SARV-seose, kasti- ja proovifoto, õhiku, keemia, mineraloogia,
granulomeetria, spektraalanalüüsi ning karbonaatsuse olemasolu.
Allikavalikud **Maavarade register** ja **Geoloogiafond** otsivad otse
WFS-teenusest ka maardlaid, aktiivseid mäeeraldisi, aktiivseid uuringualasid
ning Geoloogiafondi uuringualasid. Neid saab leida nime või registri ID järgi
ka tervikkihti eelnevalt laadimata. Geoloogiafondi tulemuse avamine lisab
ainult valitud `egf_id` filtriga piirjoonkihi.

GEA `sarv_id` käsitletakse SARV puursüdamiku võõrvõtmena ega võrrelda sama
numbriga lokaliteedi või uuringupunkti ID-ga. Muudel juhtudel kinnitatakse EGT
ja SARV automaatne seos ainult tugeva ning ühese tõendi korral, näiteks ametliku
tunnuse või lähestikku asuvate samanimeliste/-numbriliste punktide põhjal.
Ebaselged vasted kuvatakse kandidaatide loendina ega lisa andmeid automaatselt.
Kasutaja saab kandidaadi käsitsi kinnitada; kinnitus salvestatakse QGIS-i
kasutajaprofiili ja seda saab hiljem eemaldada.

Üldandmete **SARV seose haldus** real saab EGT objekti siduda SARV puursüdamiku,
lokaliteedi või uuringupunktiga. Valitakse objektitüüp ja selle SARV ID.
Qeoloog kontrollib enne salvestamist, et õiget tüüpi objekt SARV-is eksisteerib.
Parandus salvestub kohaliku QGIS-i kasutajaprofiili koos EGT võtme, algse GEA
`sarv_id`, SARV objektitüübi ja ID ning muutmise ajaga ja läheb kohe seotud
andmete laadimisel käiku. Nii saab näiteks EGT läbilõiget ja SARV lokaliteediga
seotud puursüdamikukaste samas vaates koos kuvada. **Taasta GEA seos** eemaldab
kohaliku paranduse. Kõik kohalikud parandused saab **Kihid** paanist koondatult
CSV- või JSON-failina eksportida.

Samal real saab märkida vigaseks GEA lähteandmes oleva `sarv_id` seose ja
Maa-ameti/MaRu ID seose. `ma_orig_id` on EGT–MaRu võõrvõti; SARV
`land_board_id` jääb sõltumatuks kontrolltunnuseks. Vigaseks märgitud
ID-d ei kasutata enam automaatse vaste kinnitamiseks, kuid muud sõltumatud
tõendid, näiteks asukoht, number ja sügavus, võivad endiselt anda võimaliku
kandidaadi. Märked säilivad QGIS-i kasutajaprofiilis ja sisalduvad SARV seoste
CSV/JSON-ekspordis koos MaRu käsitsi määratud ID-ga.

Kohalik käsitsi kinnitatud seos töötab mõlemas suunas. Seotud SARV objekti
avamisel laadib Qeoloog automaatselt sama GEA objekti ühendvaate. Nii kuvatakse
läbilõikel ka GEA sügavusega proovid, sealhulgas lähteandmes proovina kirjeldatud
käsipalad, ning analüüsid; SARV sügavusega eksemplarid jäävad eraldi **SE**
rajale. Sügavuseta kirjeid läbilõikele ei paigutata.

Läbilõiget saab vertikaalselt suumida Windowsis `Ctrl` + kerimisratas ja macOS-is
`Command` + kerimisratas. Tulba laius ei muutu. Uue objekti avamisel jääb viimati
valitud andmepaan avatuks.

Litoloogiliste üksuste piirid jätkuvad piiri sügavuse väärtusest paremale õrna
juhtjoonena kuni litoloogia veeruni. Juhtjooned jäävad tekstide, proovide,
analüüside ja eksemplaride taha. P, A, SP, SA ja SE raja väljalülitamisel
eemaldatakse ka selle veeru ruum ning läbilõige muutub horisontaalselt
kompaktsemaks.

Läbilõike stratigraafia, litoloogia ja sügavuste esmase allika saab **Kihid**
paanis valida. **WFS** laadib kiiremini; **API** saab GEA uuendused üldjuhul
varem kätte. Puuraukude puhul kasutatakse valitud esmase allika tõrke korral
teist allikat automaatselt varuallikana. Avalik GEA API ei paku praegu
vaatluspunktide detailandmeid, mistõttu laaditakse nende läbilõige alati
WFS-ist.
Läbilõike veerud kuvatakse järjestuses sügavused, indeks, P, A, SP, SA, SE ja
litoloogia. Vaatluspunktidel sisaldab indeksi veerg ka geneesi (näiteks
`Q1jr3 · lg`) ning SP, SA ja SE rajad ja nende lülitid on peidetud. Puuraugule
tagasi minnes taastuvad SARV-radade varasemad lülitivalikud. Genees kuvatakse
ka vaatluspunkti koondläbilõike indeksiteksti juures.

PA nupp on teistest tööriistariba nuppudest rõhutatud. Puuraukude ja
vaatluspunktide kihid hoitakse uute kihtide lisamisel alati kihipuu tipus.
Aluskorra avamuste kihile rakendatakse EGT WMS-i liiga kitsa reklaamitud
ulatuse tõttu Saaremaa lääneosa säilitav ulatuse parandus.

## Paigaldamine

1. Ava QGIS-is **Plugins → Manage and Install Plugins…**.
2. Vali **Install from ZIP**.
3. Vali `Qeoloog.zip` ja vajuta **Install Plugin**.
4. Luba plugin; QGIS-i ilmuvad tööriistariba ja menüü **Qeoloog**.

Plugin eeldab QGIS 4.x versiooni ja internetiühendust. Andmeallikad on Maa- ja
Ruumiamet, Eesti Geoloogiateenistus, SARV ning EELIS/VEKA avalik API ja teised
plugina kataloogis nimetatud avalike teenuste valdajad.

## License

Qeoloog is licensed under the GNU General Public License, version 2 or any
later version (GPL-2.0-or-later). Contact: `tavo.ani@icloud.com`.

- Source code: <https://github.com/tavoani/Qeoloog>
- Issue tracker: <https://github.com/tavoani/Qeoloog/issues>
