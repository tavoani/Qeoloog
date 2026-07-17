# Qeoloog 3.6.1

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
Puuraukude nimed kuvatakse vaikimisi 5 pt sildina 0,6 mm valge puhvriga.
Vajuta **i**, seejärel klõpsa kaardil puuraugul või vaatluspunktis.
Hetkel avatavat punkti tähistab kaardil kerge halo. Objektivaade sisaldab:

- WFS-i üldatribuute; klikitavad on ainult `gea_id`, `kande_alus_nr` ning
  olemasolu või ühese vaste korral eraldi SARV-link;
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

EGT ja SARV automaatne seos kinnitatakse ainult tugeva ning ühese tõendi korral,
näiteks ametliku tunnuse või lähestikku asuvate samanimeliste/-numbriliste
punktide põhjal. Ebaselged vasted kuvatakse kandidaatide loendina ega lisa
andmeid automaatselt. Kasutaja saab kandidaadi käsitsi kinnitada; kinnitus
salvestatakse QGIS-i kasutajaprofiili ja seda saab hiljem eemaldada.

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
