# Qeoloog 3.21.2

Qeoloog on QGIS 4 rakendus EGT GEA ja SARV geoloogiaandmete ning EELIS/VEKA
puurkaevuandmete kuvamiseks, seostamiseks ja uurimiseks. Lisaks saab avada ja
seadistada Maa- ja Ruumiameti (MaRu) ning teiste avalike andmeallikate WMS/WFS
teenuseid.

## English

Qeoloog is a QGIS 4 application focused on viewing, linking and exploring
geological data from the Geological Survey of Estonia (EGT) GEA database and
the SARV geoscience data platform, as well as EELIS/VEKA water-well data. It
provides an interactive view of
boreholes and observation points, including geological logs, drill-core boxes
and images, samples, analyses, specimens, attachments and literature.

The plugin also provides configurable access to WMS and WFS services from the
Estonian Land and Spatial Development Board (MaRu) and other public data
providers. The user interface can be displayed in Estonian or English.
Validated EGT–SARV link corrections can associate an EGT object with a SARV
drill core, locality or research site. They are stored locally, applied
immediately to the combined detail view, restored to the original GEA link and
exported together as CSV or JSON.
The geological profile draws subtle boundary guides from each boundary-depth
label towards the lithology column. Hidden P, A, SP, SA and SE tracks are also
removed from the horizontal layout so the profile becomes more compact.
An optional **Apply filters** control filters profile markers with the active
EGT and SARV sample, analysis and specimen-type filters. EGT map filters also
include the complete official stratigraphic-index list and a partial
**Contains** query across ordinary and compound indices.

The compact **Cross-sections** tab opens or hides a separate resizable
cross-section window. It combines selected EGT boreholes and observation
points, SARV drill cores and VEKA water wells on shared absolute-elevation and
distance axes without forcing the main Qeoloog dock to become wider. A section
can follow a line drawn on the map, the object order, or equal spacing.
Geological units, drill-core boxes, samples, analyses, specimens, VEKA
construction and static water levels can be switched independently. A loaded
local DEM raster can be sampled along the section line and compared visually
with recorded wellhead elevations. The result is stored in the QGIS project
and can be exported to SVG or PDF with an optional overview map.

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
- muuta objektide järjekorda, pöörata läbilõige ümber, objekt eemaldada või
  puuduva/ebatäpse absoluutkõrguse käsitsi määrata;
- kuvada tulbad ühisel absoluutkõrguse skaalal ning tegeliku piketi ja
  läbilõikejoonest kõrvalekaldega;
- lülitada eraldi indekseid, litoloogiat, piire, puursüdamikukaste, proove,
  analüüse, eksemplare, VEKA konstruktsiooni, staatilist veetaset ja suudmeid;
- hoida läbilõikejoont kaardil nähtavana;
- eksportida SVG- või A3 PDF-faili, soovi korral koos QGIS-i kaardi
  ülevaateaknaga.

Läbilõike olek salvestub QGIS-i projekti. Horisontaalset ja vertikaalset
mõõtkava saab muuta paanil olevatest väljadest; joonise kohal muudab
`Ctrl`/`Command` + kerimisratas vertikaalset ning `Alt` + kerimisratas
horisontaalset mõõtkava.

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
- otstarbe ja põhjaveekogumi mitmikvalikuga;
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
The VEKA tab filters wells by text, purpose, groundwater body, drilling year,
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
source-specific tabs. Reset clears the search criteria, result table and this
temporary filter.

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
Puuraukude nimed kuvatakse vaikimisi 5 pt sildina 0,6 mm valge puhvriga.
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

Eraldi **SARV filtrid** paanis saab lülitada lokaliteete, uuringupunkte ja
puursüdamikke, piirata tulemust kaardiulatuse ja sügavusega ning valida
puursüdamiku, proovide, analüüside või eksemplaride olemasolu. Proovi eesmärk
ja tüüp, analüüsimeetod ning eksemplari tüüp on mitmikvalikud. Mahukad seotud
andmed päritakse SARV serverist alles filtri rakendamisel.

**Otsing** leiab samast tabelist laaditud EGT puuraugud/vaatluspunktid ja SARV
kohad nime, numbri või ID, kaardiulatuse, sügavuse ning proovi- või
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
**Lähtesta** puhastab otsingutingimused, tulemused ja otsingufiltri.

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
Maa-ameti/MaRu ID (`ma_orig_id` ↔ SARV `land_board_id`) seose. Vigaseks märgitud
ID-d ei kasutata enam automaatse vaste kinnitamiseks, kuid muud sõltumatud
tõendid, näiteks asukoht, number ja sügavus, võivad endiselt anda võimaliku
kandidaadi. Märked säilivad QGIS-i kasutajaprofiilis ja sisalduvad SARV seoste
CSV/JSON-ekspordis.

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
litoloogia.

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
