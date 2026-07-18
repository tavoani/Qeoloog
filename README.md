# Qeoloog 3.9.0

Qeoloog on QGIS 4 rakendus eelkõige EGT GEA ja SARV andmebaaside
geoloogiaandmete kuvamiseks, seostamiseks ning uurimiseks. Lisaks saab avada ja
seadistada Maa- ja Ruumiameti (MaRu) ning teiste avalike andmeallikate WMS/WFS
teenuseid.

## English

Qeoloog is a QGIS 4 application focused on viewing, linking and exploring
geological data from the Geological Survey of Estonia (EGT) GEA database and
the SARV geoscience data platform. It provides an interactive view of
boreholes and observation points, including geological logs, drill-core boxes
and images, samples, analyses, specimens, attachments and literature.

The plugin also provides configurable access to WMS and WFS services from the
Estonian Land and Spatial Development Board (MaRu) and other public data
providers. The user interface can be displayed in Estonian or English.
Validated EGT–SARV link corrections can associate an EGT object with a SARV
drill core, locality or research site. They are stored locally, applied
immediately to the combined detail view, restored to the original GEA link and
exported together as CSV or JSON.

The **Personal** tab manages a standards-compliant local GeoPackage for private
samples, specimens, analyses and results. Laboratory CSV, TSV and XLSX files
are imported through a preview and explicit column-mapping step. Personal
records can be displayed beside EGT and SARV records and exported as auditable
GEA- or SARV-shaped converter packages containing CSV tables, a manifest and a
validation report.

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

**LK** avab lisakihtide menüü. Seal on aluskaardid, geoloogia, uuringute ja
maavarade kihid ning abikihid, muu hulgas kitsenduste vööndid. Menüü linnuke
lisab või eemaldab kihi.
Kui LK-menüüst lisatud kiht on projektis aktiivne, ilmub selle nupp ajutiselt
otse tööriistaribale. Ajutise nupu vajutamine eemaldab kihi ja nupp kaob; kihi
püsiv asukoht jääb endiselt tema kodurippmenüüsse.

## Seadistamine

Hammasratta alt saab:

- valida kogu kasutajaliidese eesti või inglise keele;
- näidata või peita LK rippmenüüde rühmi;
- paigutada iga kihi põhiribale, tema kindlasse kodurippmenüüsse või keelata;
- lisada ja eemaldada WMS/WFS kihte ning SARV punktikataloogi;
- lugeda GetCapabilities-kihiloendi;
- muuta tähist, värvi, nime, URL-i, kihinime ja WMS-stiili;
- lülitada sisse režiimi, kus otsenupu korduv vajutus eemaldab kihi;
- taastada Qeoloogi vaikekataloogi.

Kihi kodurühm on pärast loomist lukus: näiteks katastriüksuseid ei saa tõsta
geoloogia rühma. Seadistus säilib QGIS-i kasutajaprofiilis.

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
ja tüüp ning analüüsimeetod on mitmikvalikud. Mahukad seotud andmed päritakse
SARV serverist alles filtri rakendamisel.

**Otsing** leiab samast tabelist laaditud EGT puuraugud/vaatluspunktid ja SARV
kohad nime, numbri või ID, kaardiulatuse, sügavuse ning proovi- või
analüüsitunnuste järgi. Otsingus saab eraldi valida objektitüübid ning
puursüdamiku, proovide ja analüüside olemasolu. Tulemust saab nupust kaardil
avada ja objektivaatesse laadida ilma kaardi mõõtkava muutmata. Täpsed numbri-
ja ID-vasted ning nimevasted kuvatakse enne osalisi vasteid. Kuvatakse kuni 500
esimest vastet ning allikad ei liideta ilma kinnitatud vasteta üheks kirjeks.

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
kohaliku paranduse.

## Isiklikud andmed

Paan **Isiklik** võimaldab luua või avada Qeoloogi isikliku GeoPackage'i. See
sisaldab eraldi atribuudikihte andmekogumitele, objektiseostele, proovidele,
eksemplaridele, analüüsidele, analüüsitulemustele, manustele ja
impordipartiidele. Kirjetel on GeoPackage'i `fid` ning ekspordiks ja seosteks
stabiilne UUID. Isiklikud proovid, analüüsid ja eksemplarid ilmuvad avatud EGT
või SARV objekti vastavates paanides allikaga **MINU** ja neid saab allika
linnukesest sisse või välja lülitada. Sügavusega kirjed kuvatakse ka läbilõikel
eraldi **IP**, **IA** ja **IE** radadel ning neid saab **MINU** kontrollreal
ükshaaval sisse või välja lülitada.

Laboriandmeid saab importida CSV-, TSV- või XLSX-failist. XLSX puhul loetakse
esimene tööleht. Enne salvestamist näitab Qeoloog kuni 20 rea eelvaadet ja
veerukaardistust; kohustuslikud on proovi tähis, analüüsinäitaja ja tulemuse
väärtus. Toetatud on nii pikk vorm (üks analüüsitulemus real) kui lai vorm
(näitajad, näiteks SiO₂ ja Fe₂O₃, eraldi veergudes). Laia vormi
tulemuseveerud valib kasutaja enne importi. Valikulised väljad hõlmavad muu
hulgas analüüsi koodi, eksemplari
tähist, sügavusintervalli, ühikut, meetodit, laborit, kuupäeva, määramispiiri ja
määramatust. Vigased või puuduliku võtmeinfoga read lähevad impordiaruandesse,
mitte ei seostu vaikides vale väljaga.

Samast paanist saab:

- eksportida isiklikud andmed GEA-kujulise ZIP-konverteripaketina
  (`proov.csv`, `analyys_mootmine.csv`, `analyys_tulem.csv`);
- eksportida SARV-kujulise ZIP-konverteripaketina (`sample.csv`,
  `specimen.csv`, `analysis.csv`, `analysis_results.csv`);
- eksportida kohalikud EGT–SARV seoseparandused ühe CSV- või JSON-failina.

Mõlemad konverteripaketid sisaldavad `manifest.json` ja `validation.csv`.
Need on kontrollitavad vaheformaadid, mitte automaatne kirjutamine GEA või SARV
andmebaasi: enne sihtbaasi importi tuleb kontrollida asutuse klassifikaatorid,
objektide ID-d ja kohustuslikud väljad.

Läbilõiget saab vertikaalselt suumida Windowsis `Ctrl` + kerimisratas ja macOS-is
`Command` + kerimisratas. Tulba laius ei muutu. Uue objekti avamisel jääb viimati
valitud andmepaan avatuks.

Läbilõike stratigraafia, litoloogia ja sügavused laaditakse esmalt EGT WFS-ist.
GEA API-d kasutatakse varuallikana ainult siis, kui WFS-päring ebaõnnestub.
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
Ruumiamet, Eesti Geoloogiateenistus ning teised plugina kataloogis nimetatud
avalike teenuste valdajad.

## License

Qeoloog is licensed under the GNU General Public License, version 2 or any
later version (GPL-2.0-or-later). Contact: `tavo.ani@icloud.com`.

- Source code: <https://github.com/tavoani/Qeoloog>
- Issue tracker: <https://github.com/tavoani/Qeoloog/issues>
