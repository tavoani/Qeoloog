# Portali redigeerimise tehniline arhiiv

Staatus: **Qeoloog 3.37.0-st välja lülitatud** (30.09.2026).

See dokument säilitab tulevase eraldi kooskõlastatud rakenduse jaoks Qeoloogis
varem kasutatud Portali kirjutamistöövoogude tehnilise ulatuse. Aktiivne plugin
ei kuva redigeerimisnuppe, märgib enda kaudu avatud ArcGIS FeatureServeri kihid
kirjutuskaitstuks ning blokeerib `applyEdits`, QGIS-i redigeerimisseansi ja
välitööimpordi kirjutamisteed.

Arhiiv **ei sisalda** Client Secreti, kasutajanime, parooli, OAuth-tokenit ega
QGIS-i master-parooli. Autentimine jääb QGIS-i krüpteeritud autentimishoidlasse
ja aktiivne Qeoloog säilitab üksnes valitud `authcfg` tunnuse.

## Säilitatud skeem ja töövood

- Faktika tööruumid: põhiobjekt `Puurauk/vaatluspunkt` ning seotud tabelid
  `Isik`, `Manuse märksõnad`, `Manus`, `Juurdepääsu alus` ja
  `Geoloogiline üksus`.
- Testteenuse kihi- ja tabeli-ID-d avastatakse REST-metainfost nime järgi;
  tootmisteenuse numeratsiooni ei eeldata.
- Põhiobjekti endine töövoog hõlmas PointZ X/Y/Z koordinaate, objekti tüüpi,
  täpsusklassi, alust, metaandmeid ning puuraugu, maismaa vaatluspunkti ja mere
  vaatluspunkti väljade nähtavusreegleid.
- Geoloogilise üksuse endine töövoog hõlmas suhtelisi ja absoluutseid Z1/Z2
  väärtusi, paksust, üksust, geneesi, indeksit, kihistikku, litoloogiat,
  litoloogia täiendit, autorit ning aluse viidet.
- Liitüksus kasutas eraldi ülemist ja alumist indeksit ning nende kihistikke.
- Uus intervall päris eelmiselt realt üksuse, autori, aluse ja aluse numbri;
  kasutaja sai väärtusi enne salvestamist muuta.
- Kontrolliti kohustuslikke välju, live-domeene, sügavuste kasvu, intervallide
  kattumist, kogusügavust, pinnakatte geneesi ja geoloogilist järjekorda:
  pinnakate ei tohtinud järgneda aluspõhjale või aluskorral ning aluspõhi ei
  tohtinud järgneda aluskorral.
- Üksuse prioriteet põhiobjektil oli aluskord, aluspõhi, pinnakate, muu.
- `0` asendati teadmata väärtusega; erikoodid `997` ja `998` kuvati
  domeenisiltidena **Teadmata** ja **Ei kohaldu**.
- Z1/Z2 absoluutkõrgus ja paksus tuletati objekti Z-st ning suhtelistest
  sügavustest. Objekti pikkus tuletati kõige alumisest geoloogilisest piirist.
- SARV kandidaate ei rakendatud vaikimisi; kasutaja pidi vaste kinnitama.
  Kohalik seosehaldur ei kirjutanud Portali `sarv_id` välja varjatult üle.
- Auditväljad (`lisaja`, `lisamise_aeg`, `muutja`, `muutmise_aeg` ning ArcGIS-i
  standardsed editor-tracking väljad) jäeti serveri täita.
- Samaaegse muutmise kaitseks võrreldi enne salvestamist viimast muutmisaega.
- Seotud kirjed saadeti ühe `applyEdits` tehinguna `useGlobalIds=true` ja
  `rollbackOnFailure=true` seadistusega.
- Geofüüsika välitööde CSV import luges `x`, `y`, `z` punkte, moodustas üle
  50 m vahede kohalt katkestatud Z-toega multipart-joone ning kasutas meetodi,
  seadme ja vastutaja live-domeene.
- QGIS-i üldine Portali redigeerimine kasutas teenuse `AddFeatures`,
  `ChangeAttributeValues`, `ChangeGeometries` ja `DeleteFeatures` võimekusi.

## Kirjutuskaitstud aktiivne lahendus

- OAuth-sisselogimine ja kasutajale nähtavate teenuste kataloog säilivad.
- FeatureServeri kihid, Faktika tööruumid ja seotud tabelid avatakse vaatamiseks.
- Serverilegendid, kaardisildid, objektivaade, manused, domeenisildid,
  kõrguskontrolli vaatamisosa ja läbilõiked säilivad.
- Qeoloogi kohalikud parandused jäävad kohalikuks ning neid saab eksportida;
  need ei muuda EGT, SARV ega ArcGIS Portali lähteandmeid.

## Võimalik tulevane taastamine

Taastamine nõuab EGT selget uut kooskõlastust, eraldi turva- ja õiguste auditit,
kirjutustestide kordamist testteenuses ning kasutajaliidese uut kinnitamist.
Tehnilised kontrollpunktid on `PORTAL_EDITING_ENABLED`,
`portal_edit_operations`, Faktika redaktori salvestus, geofüüsika import ja
`NetworkClient.apply_arcgis_service_edits`. Neid ei tohi aktiivses avalikus
paketis sisse lülitada pelgalt kasutajaseadega.
