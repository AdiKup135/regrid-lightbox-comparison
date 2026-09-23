# Refreshing the ADU ordinance corpus

This guide is for whoever keeps `corpus/` current. It covers where each
document lives, when to check, how to spot a change cheaply, how to
re-fetch, and what to do once something has changed. Commands run from
`zoning-ordinances/harvest/` with `python3`. Python's own HTTPS has no CA
bundle on the build machine, so every fetcher shells out to `curl`.

## 1. Where each jurisdiction's documents live

The source of truth for this table is `harvest/targets.json`. Regenerate it
with `python3 targets_table.py`. "Chrome" means only real Chrome can read the
host; section 4 explains how.

| Jurisdiction | Platform / transport | Change marker at last fetch | Tier URLs |
|---|---|---|---|
| Atherton | municipal.codes (OpenGov) / chrome | current through Ordinance 679, passed May 20, 2026. | ADU: <https://atherton.municipal.codes/Code/17.52><br>Definitions: <https://atherton.municipal.codes/Code/17.60><br>SF standards: <https://atherton.municipal.codes/Code/17.32> <https://atherton.municipal.codes/Code/17.38> <https://atherton.municipal.codes/Code/17.42> |
| Contra Costa County (unincorporated) | Municode (CivicPlus) / chrome | VERSION: MAY 28, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV82GERE_CH82-24ACDWUN><br>Definitions: <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV82GERE_CH82-4DE><br>SF standards: <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV82GERE_CH82-10LO> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV82GERE_CH82-12SE> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV82GERE_CH82-14YA> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV84LAUSDI_CH84-4SIMIREDI> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV84LAUSDI_CH84-6SIMIREDI> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV84LAUSDI_CH84-8R-SIMIREDI> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV84LAUSDI_CH84-10R-SIMIREDI> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV84LAUSDI_CH84-12R-SIMIREDI> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV84LAUSDI_CH84-14R-SIMIREDI> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV84LAUSDI_CH84-16R-SIMIREDI> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV84LAUSDI_CH84-18R-SIMIREDI> <https://library.municode.com/ca/contra_costa_county/codes/ordinance_code?nodeId=TIT8ZO_DIV84LAUSDI_CH84-20R-SIMIREDI> |
| Fairfax | American Legal Publishing (codelibrary.amlegal.com) / chrome | 2026 S-20 (current) | ADU: <https://codelibrary.amlegal.com/codes/fairfax/latest/fairfax_ca/0-0-0-7248><br>Definitions: <https://codelibrary.amlegal.com/codes/fairfax/latest/fairfax_ca/0-0-0-6218> <https://codelibrary.amlegal.com/codes/fairfax/latest/fairfax_ca/0-0-0-30393><br>SF standards: <https://codelibrary.amlegal.com/codes/fairfax/latest/fairfax_ca/0-0-0-8246> <https://codelibrary.amlegal.com/codes/fairfax/latest/fairfax_ca/0-0-0-8316> <https://codelibrary.amlegal.com/codes/fairfax/latest/fairfax_ca/0-0-0-9323> <https://codelibrary.amlegal.com/codes/fairfax/latest/fairfax_ca/0-0-0-9500> <https://codelibrary.amlegal.com/codes/fairfax/latest/fairfax_ca/0-0-0-9657> |
| Healdsburg | eCode360 (General Code) / chrome | Includes legislation through 06-15-2026. | ADU: <https://ecode360.com/48343648><br>Definitions: <https://ecode360.com/48345046><br>SF standards: <https://ecode360.com/48342658> |
| Hillsborough | Municode (CivicPlus) / chrome | VERSION: JUN 18, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/hillsborough/codes/code_of_ordinances?nodeId=TIT17ZO_CH17.52ACDWUNJUACDWUN><br>Definitions: <https://library.municode.com/ca/hillsborough/codes/code_of_ordinances?nodeId=TIT17ZO_CH17.08DE> <https://library.municode.com/ca/hillsborough/codes/code_of_ordinances?nodeId=TIT1GEPR_CH1.04GEPR><br>SF standards: <https://library.municode.com/ca/hillsborough/codes/code_of_ordinances?nodeId=TIT17ZO_CH17.24RESEAR> <https://library.municode.com/ca/hillsborough/codes/code_of_ordinances?nodeId=TIT17ZO_CH17.28HELI> <https://library.municode.com/ca/hillsborough/codes/code_of_ordinances?nodeId=TIT17ZO_CH17.32RESTSILOCO> |
| Lafayette | Municode (CivicPlus) / chrome | VERSION: JAN 9, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/lafayette/codes/code_of_ordinances?nodeId=TIT6PLLAUS_PT2GERE_CH6-5GEPR_ART3ACDWUN><br>Definitions: <https://library.municode.com/ca/lafayette/codes/code_of_ordinances?nodeId=TIT6PLLAUS_PT2GERE_CH6-3DE><br>SF standards: <https://library.municode.com/ca/lafayette/codes/code_of_ordinances?nodeId=TIT6PLLAUS_PT3LAUSDI_CH6-7SIMIREDI> |
| Los Altos | Municode (CivicPlus) / chrome | VERSION: SEP 11, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/los_altos/codes/code_of_ordinances?nodeId=TIT14ZO_CH14.14ACDWUN><br>Definitions: <https://library.municode.com/ca/los_altos/codes/code_of_ordinances?nodeId=TIT14ZO_CH14.02DE><br>SF standards: <https://library.municode.com/ca/los_altos/codes/code_of_ordinances?nodeId=TIT14ZO_CH14.06R1SIMIDI> <https://library.municode.com/ca/los_altos/codes/code_of_ordinances?nodeId=TIT14ZO_CH14.08R1SIMIDI> <https://library.municode.com/ca/los_altos/codes/code_of_ordinances?nodeId=TIT14ZO_CH14.10R1SIMIDI> <https://library.municode.com/ca/los_altos/codes/code_of_ordinances?nodeId=TIT14ZO_CH14.12R1SIMIDI> <https://library.municode.com/ca/los_altos/codes/code_of_ordinances?nodeId=TIT14ZO_CH14.13SIORSIMIOVDI> |
| Los Altos Hills | eCode360 (General Code) / chrome | Includes legislation through Ord. No. 621 adopted December 9, 2025. | ADU: <https://ecode360.com/44000032><br>Definitions: <https://ecode360.com/43999438><br>SF standards: <https://ecode360.com/43999500> |
| Marin County (unincorporated) | Municode (CivicPlus) / chrome | VERSION: MAY 28, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/marin_county/codes/municipal_code?nodeId=TIT22DECO_ARTIIISIPLGEDERE_CH22.32STSPLAUS> <https://library.municode.com/ca/marin_county/codes/municipal_code?nodeId=TIT22DECO_ARTIVLAUSDEPE_CH22.56REACDWUNPE><br>Definitions: <https://library.municode.com/ca/marin_county/codes/municipal_code?nodeId=TIT22DECO_ARTVIIIDECODE_CH22.130DE><br>SF standards: <https://library.municode.com/ca/marin_county/codes/municipal_code?nodeId=TIT22DECO_ARTIIZODIALLAUS_CH22.10REDI> <https://library.municode.com/ca/marin_county/codes/municipal_code?nodeId=TIT22DECO_ARTIIISIPLGEDERE_CH22.20GEPRDEUSST> |
| Menlo Park | eCode360 (General Code) / chrome | Includes legislation through 06-09-2026. | ADU: <https://ecode360.com/47187943><br>Definitions: <https://ecode360.com/47185724><br>SF standards: <https://ecode360.com/47186023> <https://ecode360.com/47186061> <https://ecode360.com/47186101> <https://ecode360.com/47186139> <https://ecode360.com/47186157> <https://ecode360.com/47186195> |
| Mill Valley | eCode360 (General Code) / chrome | Includes legislation through Ord. No. 1368 adopted April 20, 2026. | ADU: <https://ecode360.com/44319622><br>Definitions: <https://ecode360.com/44317695><br>SF standards: <https://ecode360.com/44317857> |
| Moraga | Municode (CivicPlus) / chrome | VERSION: JUN 1, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/moraga/codes/municipal_code?nodeId=MOCA_TIT8PLZO_CH8.124ACDWUN><br>Definitions: <https://library.municode.com/ca/moraga/codes/municipal_code?nodeId=MOCA_TIT8PLZO_CH8.04GEPRDE><br>SF standards: <https://library.municode.com/ca/moraga/codes/municipal_code?nodeId=MOCA_TIT8PLZO_CH8.21FLARRAFAST> <https://library.municode.com/ca/moraga/codes/municipal_code?nodeId=MOCA_TIT8PLZO_CH8.22RUREDIRR> <https://library.municode.com/ca/moraga/codes/municipal_code?nodeId=MOCA_TIT8PLZO_CH8.24ONTWTHDWUNPEACREDI> <https://library.municode.com/ca/moraga/codes/municipal_code?nodeId=MOCA_TIT8PLZO_CH8.68GESTLOYASEFEWA> |
| Mountain View | Municode (CivicPlus) / chrome | VERSION: AUG 17, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/mountain_view/codes/code_of_ordinances?nodeId=PTIITHCO_CH36ZO_ARTIVREZO_DIV10ACDWUN><br>Definitions: <https://library.municode.com/ca/mountain_view/codes/code_of_ordinances?nodeId=PTIITHCO_CH36ZO_ARTXVIIDE><br>SF standards: <https://library.municode.com/ca/mountain_view/codes/code_of_ordinances?nodeId=PTIITHCO_CH36ZO_ARTIVREZO_DIV3SIMIR1ZODIST> <https://library.municode.com/ca/mountain_view/codes/code_of_ordinances?nodeId=PTIITHCO_CH36ZO_ARTIVREZO_DIV12SEFLARRAEX> <https://library.municode.com/ca/mountain_view/codes/code_of_ordinances?nodeId=PTIITHCO_CH36ZO_ARTIIIGERESPPREXIN_DIV4GESE> |
| Napa | eCode360 (General Code) / chrome | Includes legislation through Ord. No. O2026-006 adopted June 16, 2026. | ADU: <https://ecode360.com/43397584><br>Definitions: <https://ecode360.com/43396147><br>SF standards: <https://ecode360.com/43396456> |
| Napa County (unincorporated) | Municode (CivicPlus) / chrome | VERSION: JUL 14, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/napa_county/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.104ADZODIRE><br>Definitions: <https://library.municode.com/ca/napa_county/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.08DE_18.08.190COLO> <https://library.municode.com/ca/napa_county/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.08DE_18.08.340LELO> <https://library.municode.com/ca/napa_county/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.08DE_18.08.590SIPA> <https://library.municode.com/ca/napa_county/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.08DE_18.08.650YA><br>SF standards: <https://library.municode.com/ca/napa_county/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.104ADZODIRE> <https://library.municode.com/ca/napa_county/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.52RSRESIDI> <https://library.municode.com/ca/napa_county/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.64RCRECODI> <https://library.municode.com/ca/napa_county/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.112ROSE> |
| Orinda | Municode (CivicPlus) / chrome | VERSION: APR 3, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/orinda/codes/code_of_ordinances?nodeId=TIT17ZO_CH17.3REDIBAUSRE_17.3.4ACDWUNAD><br>Definitions: <https://library.municode.com/ca/orinda/codes/code_of_ordinances?nodeId=TIT17ZO_CH17.2DE><br>SF standards: <https://library.municode.com/ca/orinda/codes/code_of_ordinances?nodeId=TIT17ZO_CH17.4REDIBADERE> <https://library.municode.com/ca/orinda/codes/code_of_ordinances?nodeId=TIT17ZO_CH17.6REFLAR> |
| Palo Alto | American Legal Publishing (codelibrary.amlegal.com) / chrome | Supp. No. 82 - 2026 (current) | ADU: <https://codelibrary.amlegal.com/codes/paloalto/latest/paloalto_ca/0-0-0-76738><br>Definitions: <https://codelibrary.amlegal.com/codes/paloalto/latest/paloalto_ca/0-0-0-76370><br>SF standards: <https://codelibrary.amlegal.com/codes/paloalto/latest/paloalto_ca/0-0-0-77117> <https://codelibrary.amlegal.com/codes/paloalto/latest/paloalto_ca/0-0-0-76822> |
| Portola Valley | Municode (CivicPlus) / chrome | VERSION: JUL 21, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/portola_valley/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.25STACDWUNADJUACDWUNJA><br>Definitions: <https://library.municode.com/ca/portola_valley/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.04DE><br>SF standards: <https://library.municode.com/ca/portola_valley/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.12REESDIRE> <https://library.municode.com/ca/portola_valley/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.14SIMIREDIRE> <https://library.municode.com/ca/portola_valley/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.16MOREDIRE> <https://library.municode.com/ca/portola_valley/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.48PAAROPSPBUASRE> <https://library.municode.com/ca/portola_valley/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.52YA> <https://library.municode.com/ca/portola_valley/codes/code_of_ordinances?nodeId=TIT18ZO_CH18.54BUBU> |
| San Carlos | Code Publishing (General Code) / direct | current through Ordinance 1637, passed June 22, 2026. | ADU: <https://www.codepublishing.com/CA/SanCarlos/html/SanCarlos18/SanCarlos1823.html><br>Definitions: <https://www.codepublishing.com/CA/SanCarlos/html/SanCarlos18/SanCarlos1841.html> <https://www.codepublishing.com/CA/SanCarlos/html/SanCarlos18/SanCarlos1803.html><br>SF standards: <https://www.codepublishing.com/CA/SanCarlos/html/SanCarlos18/SanCarlos1804.html> |
| San Jose | Municode (CivicPlus) / chrome | VERSION: JUL 21, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/san_jose/codes/code_of_ordinances?nodeId=TIT20ZO_CH20.80SPUSRE><br>Definitions: <https://library.municode.com/ca/san_jose/codes/code_of_ordinances?nodeId=TIT20ZO_CH20.200DE><br>SF standards: <https://library.municode.com/ca/san_jose/codes/code_of_ordinances?nodeId=TIT20ZO_CH20.30REZODI> |
| San Mateo | City-hosted (Open Law Library format) / direct | Current through June 17, 2026 Last codified ordinance City of San Mateo, Cal., Ord. No. 2026-07 | ADU: <https://law.cityofsanmateo.org/us/ca/cities/san-mateo/code/27.19><br>Definitions: <https://law.cityofsanmateo.org/us/ca/cities/san-mateo/code/27.04><br>SF standards: <https://law.cityofsanmateo.org/us/ca/cities/san-mateo/code/27.18> |
| San Mateo County (unincorporated) | County-hosted PDF (smcgov.org) / direct | PDF CreationDate Fri Apr 24 23:58:55 2026 IDT; ModDate Sat Apr 25 00:07:08 2026 IDT | ADU: <https://www.smcgov.org/media/159094/download?inline=><br>Definitions: <https://www.smcgov.org/media/159094/download?inline=><br>SF standards: <https://www.smcgov.org/media/159094/download?inline=> |
| Santa Clara County (unincorporated) | Municode (CivicPlus) / chrome | VERSION: SEP 10, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/santa_clara_county/codes/code_of_ordinances?nodeId=TITCCODELAUS_APXIZO_ART4SUSTRE_CH4.10SUUSRE><br>Definitions: <https://library.municode.com/ca/santa_clara_county/codes/code_of_ordinances?nodeId=TITCCODELAUS_APXIZO_ART1GEPR_CH1.30DEGETE><br>SF standards: <https://library.municode.com/ca/santa_clara_county/codes/code_of_ordinances?nodeId=TITCCODELAUS_APXIZO_ART2BADI_CH2.20RUBADI> <https://library.municode.com/ca/santa_clara_county/codes/code_of_ordinances?nodeId=TITCCODELAUS_APXIZO_ART2BADI_CH2.30URREBADI> |
| Saratoga | Municode (CivicPlus) / chrome | VERSION: AUG 13, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-56ACDWUN><br>Definitions: <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-06DE_15-06.290FR> <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-06DE_15-06.420LO> <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-06DE_15-06.430LOLI> <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-06DE_15-06.520PRLI> <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-06DE_15-06.587SE> <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-06DE_15-06.588SEAR> <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-06DE_15-06.590SELI><br>SF standards: <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-12SIMIREDI> <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-13HRHIREDI> <https://library.municode.com/ca/saratoga/codes/code_of_ordinances?nodeId=CH15ZORE_ART15-20REOPSPDI> |
| Sausalito | eCode360 (General Code) / chrome | Includes legislation through 04-21-2026. | ADU: <https://ecode360.com/47135313><br>Definitions: <https://ecode360.com/47137407><br>SF standards: <https://ecode360.com/47134342> |
| Sonoma County (unincorporated) | Municode (CivicPlus) / chrome | VERSION: FEB 26, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/sonoma_county/codes/code_of_ordinances?nodeId=CH26SOCOZORE_ART88GEEXSPUSST><br>Definitions: <https://library.municode.com/ca/sonoma_county/codes/code_of_ordinances?nodeId=CH26SOCOZORE_ART04GL><br>SF standards: <https://library.municode.com/ca/sonoma_county/codes/code_of_ordinances?nodeId=CH26SOCOZORE_ART08REZO> |
| Sunnyvale | eCode360 (General Code) / chrome | Includes legislation through Ord. No. 3255-26 adopted May 19, 2026. | ADU: <https://ecode360.com/42732718><br>Definitions: <https://ecode360.com/42729520><br>SF standards: <https://ecode360.com/42730352> <https://ecode360.com/42730359> <https://ecode360.com/42730405> |
| Windsor | Municode (CivicPlus) / chrome | VERSION: AUG 25, 2026 (CURRENT) | ADU: <https://library.municode.com/ca/windsor/codes/code_of_ordinances?nodeId=TITXVIIZOCO_ART7HORE_CH17.82ACDWUNAD> <https://library.municode.com/ca/windsor/codes/code_of_ordinances?nodeId=TITXVIIZOCO_ART7HORE_CH17.84JUACDWUNJA><br>Definitions: <https://library.municode.com/ca/windsor/codes/code_of_ordinances?nodeId=TITXVIIZOCO_ART8DE><br>SF standards: <https://library.municode.com/ca/windsor/codes/code_of_ordinances?nodeId=TITXVIIZOCO_ART2ZOALUSDEST_CH17.10REZO_17.10.040REZODEST> <https://library.municode.com/ca/windsor/codes/code_of_ordinances?nodeId=TITXVIIZOCO_ART2ZOALUSDEST_CH17.10REZO_17.10.050ADDESTESZO> <https://library.municode.com/ca/windsor/codes/code_of_ordinances?nodeId=TITXVIIZOCO_ART3REAPALZO_CH17.20GESIPLDEST_17.20.050SEMEEX> |

**How each host signals change:**

| Host | Change marker | Where the marker is read |
|---|---|---|
| Municode (15 jurisdictions) | Publication version: "VERSION: <date> (CURRENT)" on the page, and supplement name plus online date | `https://library.municode.com/localapi/PublicationVersion/GetViewModel/<ClientID>/<code name>`, an open endpoint that curl can read. `ClientID` comes from `/localapi/Organizations/GetByUrlEncodedNames/ca/<client>` |
| eCode360 (7) | "Includes legislation through Ord. No. X adopted <date>" (or "through <date>") | Embedded in every chapter page's version JSON. The "New Laws" box lists adopted laws not yet codified, and is stored in `host_notes` |
| Code Publishing (San Carlos) | "current through Ordinance N, passed <date>." | Code home page, e.g. <https://www.codepublishing.com/CA/SanCarlos/>, readable by curl with the old Chrome 91 UA |
| American Legal (Fairfax, Palo Alto) | Version label "2026 S-20 (current)" or "Supp. No. 82 - 2026 (current)" | Rendered page only, in the version dropdown |
| municipal.codes (Atherton) | "current through Ordinance N, passed <date>." | Every page, via same-origin fetch in Chrome |
| Open Law Library (San Mateo) | "Current through <date> Last codified ordinance … Ord. No. N", plus the head commit of the bulk-download repo | <https://law.cityofsanmateo.org/us/ca/cities/san-mateo/code> and `github.com/cityofsanmateo/law-html` |
| County PDF (San Mateo County) | The PDF's own sha256, HTTP Last-Modified, and PDF creation date. The county publishes Title 8 as one PDF | <https://www.smcgov.org/planning/zoning-regulations>. Check the page's "Title 8" link, because the media id changes when the county re-uploads |

**Adopted but not yet codified as of 2026-09-23.** The corpus holds the
codified text. These amendments are reported, not merged:

- **Sunnyvale:** Ord. 3258-26, adopted 2026-07-28, amends Ch. 19.32, 19.79 (ADU) and 19.80. It is in eCode360's New Laws; the codification runs through Ord. 3255-26.
- **Moraga:** Ord. No. 321, adopted 2026-07-08, amends Ch. 8.124 ADU. It is on Municode's recent-ordinances list.
- **Sausalito:** Ord. 15-2025, adopted 2025-11-04, amends Title 10. It is in eCode360's New Laws.

## 2. When to refresh

State ADU law changes take effect on January 1 each year, and cities
usually amend their codes over the following 6 to 12 months. Code hosts
publish a supplement weeks to months after adoption.

**Scheduled checks:**

- **Quarterly change-marker check** in January, April, July and October. It
  takes minutes and fetches no documents. Run `check_markers.py` (section 3)
  and re-fetch only jurisdictions that show CHANGED.
- **Full re-fetch every January and July.** Re-fetch all three tiers for all
  28 jurisdictions, even where no marker moved. This catches silent edits a
  marker doesn't announce, such as table corrections or renumbered sections.

**Event triggers.** Run the marker check for the affected jurisdictions
right away, and re-fetch once their host shows the change:

- **A state ADU bill is signed**, usually September to October. Expect
  local amendments in the next year and check monthly from the following
  January until each affected city's host moves.
- **A council or board agenda carries an ADU or zoning amendment** for one of
  the 28. Recheck after second reading, then after the host's next
  supplement.
- **A reviewer disputes an engine result.** Check that jurisdiction's marker
  and its New Laws or pending list before re-examining the engine.
- **A pending amendment listed in section 1 is codified.** The Sunnyvale,
  Moraga and Sausalito markers will move when their host publishes it.
- **A host migrates.** This has already happened to Sausalito, Healdsburg
  and Menlo Park, all moved from Code Publishing to eCode360. A 404, a
  redirect stub, or a "General Code" error page means you must find the new
  host, update `targets.json`, and re-fetch.

## 3. Detecting change cheaply

```bash
cd zoning-ordinances/harvest
python3 check_markers.py
```

This checks the 21 jurisdictions whose markers curl can read: all 15
Municode, plus San Carlos, San Mateo and San Mateo County. It prints `same`,
`CHANGED` or `unknown` for each and writes `corpus/markers-observed.json`.
The seven eCode360 cities, the two American Legal cities and Atherton print
`unknown` until their markers are read in Chrome:

1. **eCode360.** In any Chrome tab on `ecode360.com`, paste
   `browser/markers.js` into the JavaScript console (or the Claude Chrome
   tool) and run `await formxMarkers.ecode360()`.
2. **municipal.codes.** In a tab on `atherton.municipal.codes`, run
   `await formxMarkers.municipalCodes()`.
3. **American Legal.** Open each code page and run
   `formxMarkers.amlegalHere("fairfax")`, then `("palo-alto")`.
4. **Fold them in.** Save the returned arrays together as one JSON array in
   `obs.json`, then run:

```bash
python3 check_markers.py --observed obs.json
```

**Material change.** A marker change only means the host published
something. After re-fetching:

- **Raw hash unchanged:** nothing changed, so update only `fetched` and the
  marker.
- **Raw hash changed but text hash unchanged:** the host changed page chrome
  or scripts, which is not material.
- **Text hash changed:** diff the text (section 5). The change is material
  if it touches any number, table cell, qualifier ("shall", "may", "except",
  "only", "at least", "no more than"), a defined term, a cross-reference, a
  district name or list, or the applicability of a rule. Re-flowed
  whitespace or a new history note alone is not material, but record the
  history note, because it names the amending ordinance.

## 4. How to run it

**One-time setup.**

- **The receiver.** Start it in a terminal and leave it running:

```bash
cd zoning-ordinances/harvest
python3 sink.py
```

  It listens on `127.0.0.1:8770`, receives pages from Chrome, re-hashes
  every part, and refuses any part whose bytes don't match the sha256 Chrome
  computed before sending. It also serves `GET /wait?ms=N`, which the page
  script uses as a pause, because Chrome throttles timers in background
  tabs.
- **Chrome site permissions.** In Chrome, open the site-controls icon, then
  Site settings, for each Chrome host. Set both local-network entries to
  Allow: "Local network access" and the loopback, or apps-on-this-device,
  entry. The hosts are `ecode360.com`, `library.municode.com`,
  `codelibrary.amlegal.com` and `atherton.municipal.codes`. Without them the
  page's request to the receiver hangs. You can test from the page console:
  `await navigator.permissions.query({name:"loopback-network"})` must return
  `granted`. Reload the tab after changing a permission.

**Curl hosts** are Code Publishing, San Mateo and San Mateo County:

```bash
python3 fetch_direct.py san-carlos san-mateo san-mateo-county
```

- **Code Publishing** needs the old Chrome 91 user agent, which is pinned in
  `corpuslib.UA_OLD`. It returns 403 to a current Chrome UA.
- **San Mateo** is fetched from its bulk-download mirror,
  `github.com/cityofsanmateo/law-html`, on the default branch. The library's
  home page asks visitors not to scrape and to use that download instead.
  The fetcher reads each chapter's contents page and follows every section
  link, so added or renumbered sections are picked up.
- **San Mateo County** is one PDF. If the county re-uploads it, update the
  media URL in `targets.json`. The chapter slices are regex-based
  ("CHAPTER 8.392 …"), so renumbering needs an edit there.

**Chrome hosts.** Use the Claude Chrome tools or the DevTools console. In a
tab on the host, paste `browser/grab.min.js` once per full page load. It is
the minified `browser/grab.js`, the readable source. Then, per host:

- **eCode360** is server-rendered. From any `ecode360.com` tab:
  `await formxGrab.grab(slug, doc, urls)`. It fetches each URL same-origin,
  so one tab serves every eCode360 city. The host answers HTTP 429 to
  bursts, so run one document at a time and pause between runs; the
  receiver refuses the 429 pages.
- **Municode** renders in the browser. Load the code, then
  `await formxGrab.grabNodes(slug, doc, nodeIds)`. It navigates in-app to
  each node, waits for the node's own chunk and for the content to stop
  growing, and sends the rendered `#codesContent`. It refuses "Mini TOC"
  pages, which list a node's children instead of their text; where a
  chapter is a Mini TOC, list its articles or sections as the nodes. Every
  Municode target's `nodes` in `targets.json` doubles as the text selector,
  so only those nodes' chunks reach the text.
- **American Legal** renders in the browser and lazy-loads sections. Run
  `await formxGrab.grabAm(slug, doc, nodeIds)`. It clicks the contents link,
  scrolls the section body until the number of rendered sections equals the
  chapter's own section list, and refuses the page otherwise. A same-origin
  `fetch()` returns 403 here, so the rendered DOM is what gets stored.
- **municipal.codes** is server-rendered, so use
  `await formxGrab.grab(slug, doc, urls)`. Cloudflare answers 429 to bursts;
  the Atherton URLs are few, so fetch them with pauses of about 3 seconds.

**Long runs.** The JavaScript tool times out after 45 seconds, but the
script keeps running in the page. For a document with many nodes, start it
without awaiting, as in `formxGrab.bg("grabNodes", slug, doc, nodeIds)`, and
read `window.formxResult` afterwards.

**Adding or moving a target.** Edit `targets.json`; `addmuni.py` builds a
Municode entry from a small spec. Then re-fetch.

**If the page must not reach localhost.** Save the payload JSON by any
means, then run `python3 save_doc.py payload.json`. The same sha256 check
applies.

**Why tool output is never used as a save path.** Returning page content
through the agent's tool result and writing it to disk was tried. It is too
large and error-prone for raw pages, and a hand-built bridge that sidesteps
Chrome's local-network rule was rejected by the harness's safety check. The
supported path is the receiver plus the site permissions above.

## 5. After a change

1. **Re-fetch** the changed jurisdiction's three documents, as in section 4.
   Every save re-extracts the text and rewrites the manifest record: new
   hashes, `fetched`, `host_marker`, `history_notes` and `host_notes`.
2. **Verify** integrity and determinism:

```bash
python3 verify.py
```

   It must report 0 problems: hashes, per-part hashes, re-extraction equal
   to the stored text, and no leftover site text.
3. **Diff the text** against the last committed version:

```bash
git -C .. diff --word-diff -- zoning-ordinances/corpus/<slug>/
```

   Judge materiality with the rules in section 3.
4. **If extraction broke,** check the manifest's `missing_sections`, a
   sudden drop in `chars_text`, or a definitions count of zero. Fix the
   host rule in `extract.py`'s `PLATFORMS` table or the target in
   `targets.json`, then run `python3 extract.py <slug>`. That re-extracts
   from the stored raw file without fetching. Then run `verify.py` again.
5. **Flag the jurisdiction** for the engine's value table to be
   re-verified. Record the slug, what changed (section numbers and the
   amending ordinance from the new history note), and whether the change
   touches setbacks, height, size, coverage, parking or corner-lot rules.
   The engine's local values for that jurisdiction are unverified until
   someone re-reads them against the new text and re-runs the per-provision
   state-law comparison.
6. **Commit** the corpus diff and the refreshed `markers-observed.json`
   together. Put the amending ordinance in the commit message.
