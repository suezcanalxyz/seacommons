# SeaCommons — Maritime OSINT Phase 0 implementation prompt

Lavora sulla repository GitHub suezcanalxyz/seacommons, partendo esclusivamente dall'ultimo main.

## Contesto verificato

- Il commit humanitarian ffffe12 è già confluito in main.
- Il piano corrente è docs/fixes.md introdotto dal commit 0fbd127.
- Non utilizzare né ripristinare la vecchia “Section 7”: è stata sostituita dal nuovo piano Maritime OSINT Evidence Engine.
- docs/current_work.md descrive ancora il precedente branch humanitarian e non deve essere considerato la roadmap corrente.
- Non eseguire deploy, restart, migrazioni o mutazioni del database di produzione.

## Obiettivo

Esegui la Phase 0 del nuovo docs/fixes.md e correggi prioritariamente le regressioni ancora visibili:

1. Il blocco MMSI/IMO non è completo: identificatori navali e link commerciali continuano ad apparire in alcuni casi humanitarian.
2. Un evento AIS con navigational status “unable to manoeuvre” viene trattato come caso anomalo generico o drift, mentre deve appartenere al dominio Maritime Safety / Maritime Service.
3. Categorie come pleasure craft, other vessels, cargo o tanker non devono essere presentate come anomalie: sono attributi descrittivi della nave.
4. Il sistema Maritime deve iniziare a distinguere movimenti realmente sospetti da semplici classi di nave o stati AIS.

## Procedura obbligatoria

### 1. Verifica iniziale

- Esegui git status, identifica HEAD e conferma che il lavoro parte dall'ultimo main.
- Leggi integralmente:
  - docs/fixes.md
  - docs/current_work.md
  - contratti backend/frontend delle categorie
  - pipeline AIS, anomaly detection, Live projection e rendering del pannello
- Cerca tutti i punti in cui MMSI, IMO, callsign, MarineTraffic o equivalenti entrano nelle API e nella UI pubblica.
- Cerca tutti i punti che utilizzano vessel type, vessel class o navigational status per creare un'anomalia.

Prima di modificare il codice, scrivi una breve matrice:

| Problema | Causa effettiva | File coinvolti | Test mancante |
| --- | --- | --- | --- |

Non assumere che il problema sia solo frontend.

### 2. Separazione semantica

Implementa o consolida la separazione tra:

- Vessel attributes: cargo, tanker, passenger, fishing, pleasure craft, tug, other vessel.
- Navigational status: underway, at anchor, moored, not under command, restricted manoeuvrability, constrained by draught.
- Maritime safety event: unable to manoeuvre, not under command, grounding, collision, machinery failure, distress.
- Behavioural anomaly: AIS gap, impossible movement, identity conflict, suspicious loitering, rendezvous, route deviation.
- Humanitarian incident: Alarm Phone, distress case, SAR case, land humanitarian, region-only report.

Una vessel class non deve mai creare automaticamente un'anomalia.

“Unable to manoeuvre” deve:

- essere classificato come maritime_safety o tassonomia equivalente già prevista;
- apparire nel gruppo Maritime Service/Safety;
- non generare drift SAR automatico;
- non essere trasformato in humanitarian;
- mantenere stato AIS, fonte, timestamp e nave associata come evidenza;
- essere distinto da un'anomalia comportamentale.

### 3. Privacy e separazione Humanitarian

Per tutte le superfici pubbliche humanitarian:

- non esporre MMSI;
- non esporre IMO;
- non esporre callsign;
- non mostrare MarineTraffic o link equivalenti;
- non associare automaticamente una nave AIS a una segnalazione umanitaria senza evidenza esplicita e revisionabile;
- applicare il filtro anche a payload API, feature GeoJSON, pannelli, tooltip, feed, edge payload e fallback frontend.

Le informazioni possono restare nel livello interno solo quando necessarie alla provenance o alla revisione.

Per casi terrestri border/detention:

- conserva internamente la coordinata originale;
- pubblica solo posizione degradata, area approssimata o coordinata omessa;
- aggiungi provenance della trasformazione di privacy.

Per casi Alarm Phone resolved:

- rimuovili dal Live operativo;
- conservali nell'archivio come resolved;
- mantieni la categoria humanitarian rossa;
- degrada la precisione pubblica quando necessario.

### 4. Fondamenta del motore OSINT

Implementa le parti della Phase 0 necessarie a sostenere il nuovo modello:

Observation → Feature → Episode → Hypothesis → Review

Requisiti minimi:

- ogni anomalia deve conservare osservazioni e provenance;
- nessun singolo segnale deve diventare automaticamente una conclusione;
- distinguere observed_at, received_at e processed_at;
- aggiungere reason codes leggibili dalla macchina;
- aggiungere versione del detector e dei parametri;
- distinguere insufficient_evidence, coverage_unknown, needs_review, corroborated e dismissed;
- evitare uno score opaco unico;
- mostrare all'operatore quali evidenze hanno prodotto l'episodio.

Non implementare ancora un sistema sanzionatorio o satellitare completo. Predisponi contratti ed estensioni senza introdurre dipendenze costose o dati con licenze incompatibili.

### 5. Test obbligatori

Aggiungi test di regressione che dimostrino almeno:

- nessun MMSI/IMO/callsign/link commerciale nelle risposte humanitarian pubbliche;
- nessuna fuga tramite edge payload o fallback frontend;
- unable to manoeuvre → Maritime Safety;
- unable to manoeuvre non genera humanitarian o drift;
- pleasure craft e other vessel restano attributi descrittivi;
- una normale nave cargo non genera un caso sospetto;
- un AIS gap senza informazione sulla copertura non viene dichiarato comportamento illecito;
- un'anomalia conserva osservazioni, reason codes, detector version e timestamp distinti;
- un evento resolved sparisce dal Live ma resta nell'archivio;
- coordinate terrestri sensibili vengono degradate pubblicamente.

Esegui:

- suite backend completa;
- test web simulation/live/api/map;
- lint ESLint + TypeScript;
- build Vite;
- test edge.

Riporta output e conteggi reali. Non dichiarare “green” senza aver eseguito i comandi.

### 6. Documentazione

- Aggiorna docs/current_work.md per separare chiaramente:
  - lavoro humanitarian completato;
  - debito operativo ancora aperto;
  - nuova Phase 0 Maritime;
  - decisioni applicate;
  - verifiche non eseguibili senza produzione.
- Non reinserire la vecchia Section 7.
- Aggiorna le checkbox di docs/fixes.md soltanto quando ogni requisito è coperto da codice, test e prova verificabile.
- Per drift_results intel:aa91d1a0, prepara soltanto una proposta di bonifica auditabile verso cancelled/ineligible; non modificare il database.

### 7. Vincoli

Non:

- inventare dati AIS;
- considerare vessel type come comportamento sospetto;
- equiparare rendezvous a violazione o sanzione;
- trattare un AIS gap come prova di attività illecita;
- aggiungere provider commerciali senza licensing review;
- esporre identificatori navali nei casi humanitarian;
- modificare produzione;
- fare deploy;
- riavviare servizi;
- cancellare righe DB;
- sovrascrivere modifiche non correlate.

## Consegna

Al termine:

1. mostra la matrice cause/file/test;
2. elenca tutti i file modificati;
3. mostra risultati completi delle verifiche;
4. indica checkbox aggiornate nel nuovo docs/fixes.md;
5. elenca rischi e attività ancora operator-only;
6. crea un singolo commit con messaggio chiaro, ad esempio:

   feat(maritime): establish evidence model and safety classification

7. comunica hash e URL del commit;
8. non eseguire merge o deploy senza conferma esplicita.
