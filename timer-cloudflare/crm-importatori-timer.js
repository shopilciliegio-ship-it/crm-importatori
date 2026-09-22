// worker.js — timer esterno (Cloudflare Worker) per le automazioni schedulate di crm-importatori.
//
// Perché esiste: il cron di GitHub Actions ("schedule") parte con ore di ritardo — stesso problema già
// risolto per CiliegioSocialMedia (vedi quel repo, timer-cloudflare/worker.js). La Ricerca AI importatori,
// pensata per le 7:00 del mattino, arrivava per email nel primo pomeriggio. Un "Run workflow"
// (workflow_dispatch) invece parte subito: questo Worker, che Cloudflare esegue puntuale, lancia il
// workflow giusto all'ora giusta (Europe/Rome).
//
// Un solo cron trigger: "0 4,5,6,7,8,9,10,11,16,17,22,23 * * *" (UTC — va impostato così nel pannello
// Cloudflare, Triggers). Copre ora legale e solare; il Worker guarda l'ora vera di Roma e lancia solo
// se è il momento giusto:
//   - ogni giorno 7:00 Roma  → research_ai.yml          (ricerca AI importatori + email)
//   - ogni giorno 0/6/12/18 Roma → import_ordini.yml         (import ordini Gmail + tracking + reminder)
//   - ogni giorno 0/6/12/18 Roma → sync_wave_tracking.yml    (sync aperture/click/bounce Brevo)
//   - lunedì  9:00 Roma  → spotty_weekly.yml            (import SpottyWifi + wave email)
//   - lunedì 11:00 Roma  → bwi_weekly.yml                (scrape BestWine + sync CRM)
// Gli orari UTC che non corrispondono a nessuno di questi non lanciano nulla (fanno solo perdere
// qualche invocazione del Worker, gratis su Cloudflare nel piano free fino a 100k/giorno).
//
// I 5 workflow restano anche col proprio "schedule:" di riserva (retimato sulla stessa cadenza) e con
// un "concurrency:" group a testa: se timer esterno e cron di riserva GitHub partono vicini, il secondo
// aspetta la fine del primo invece di girare in parallelo.
//
// Segreti (Worker → Settings → Variables and Secrets, tipo "Secret"):
//   GITHUB_TOKEN  token fine-grained GitHub, solo repo crm-importatori, permesso Actions: Read and write
//                 (NON lo stesso token del Worker "ciliegio-timer" di CiliegioSocialMedia: repo diverso)
//   TEST_KEY      una stringa a caso, serve solo per la pagina di prova /test/<TEST_KEY>/<job>
// Pagina /status: dice se il Worker è attivo e se i due segreti gli sono arrivati (mai i valori).

// Un secret incollato nel pannello può portarsi dietro spazi o a-capo: qui vengono ignorati.
const segreto = v => (typeof v === 'string' ? v.trim() : '');

const OWNER  = 'shopilciliegio-ship-it';
const REPO   = 'crm-importatori';
const BRANCH = 'main';

// Nessuno di questi 5 workflow ha input di workflow_dispatch (girano identici a mano, da cron o da
// questo Worker), quindi la dispatch non manda "inputs".
const JOBS = {
  research_ai:        { workflow: 'research_ai.yml',        quando: r => r.hour === 7 },
  import_ordini:      { workflow: 'import_ordini.yml',      quando: r => [0, 6, 12, 18].includes(r.hour) },
  sync_wave_tracking: { workflow: 'sync_wave_tracking.yml', quando: r => [0, 6, 12, 18].includes(r.hour) },
  spotty_weekly:      { workflow: 'spotty_weekly.yml',      quando: r => r.weekday === 'Mon' && r.hour === 9 },
  bwi_weekly:         { workflow: 'bwi_weekly.yml',         quando: r => r.weekday === 'Mon' && r.hour === 11 },
};

function romeNow(date) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Rome', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
      .formatToParts(date).map(p => [p.type, p.value])
  );
  return { weekday: parts.weekday, hour: parseInt(parts.hour, 10) % 24, minute: parseInt(parts.minute, 10) };
}

// Lancia il workflow. Errori nostri (token, permessi, nome file) → subito eccezione; errori di GitHub (5xx, 429) → 3 tentativi.
async function dispatch(env, job) {
  const url = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${JOBS[job].workflow}/dispatches`;
  const body = JSON.stringify({ ref: BRANCH });
  for (let tentativo = 1; tentativo <= 3; tentativo++) {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${segreto(env.GITHUB_TOKEN)}`,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'crm-importatori-timer',
        'Content-Type': 'application/json'
      },
      body
    });
    if (res.status === 204) return `OK: lanciato ${JOBS[job].workflow}, tentativo ${tentativo}`;
    const testo = (await res.text()).slice(0, 300);
    if (res.status < 500 && res.status !== 429) throw new Error(`GitHub ha risposto ${res.status} per ${JOBS[job].workflow}: ${testo}`);
    await new Promise(r => setTimeout(r, 2000 * tentativo));
  }
  throw new Error(`GitHub non raggiungibile per ${JOBS[job].workflow} dopo 3 tentativi`);
}

export default {
  // Chiamato da Cloudflare secondo il cron trigger.
  async scheduled(event, env) {
    const r = romeNow(new Date(event.scheduledTime));
    const lanciati = Object.keys(JOBS).filter(j => JOBS[j].quando(r));
    if (!lanciati.length) {
      console.log(`Niente da lanciare: a Roma sono ${r.weekday} ${r.hour}:${String(r.minute).padStart(2, '0')}.`);
      return;
    }
    for (const j of lanciati) console.log(await dispatch(env, j));   // se lancia eccezione l'esecuzione risulta fallita nei log di Cloudflare
  },

  // Pagina di prova: /test/<TEST_KEY>/<job> → lancia il workflow indicato subito, ignorando l'orario.
  // Con una chiave sbagliata risponde 404. /status → diagnostica non sensibile.
  async fetch(request, env) {
    const [, sezione, chiave, job] = new URL(request.url).pathname.split('/');
    if (sezione === 'status') {
      const r = romeNow(new Date());
      return new Response([
        'Worker attivo.',
        `GITHUB_TOKEN: ${segreto(env.GITHUB_TOKEN) ? 'impostato' : 'MANCANTE'}`,
        `TEST_KEY: ${segreto(env.TEST_KEY) ? 'impostata' : 'MANCANTE'}`,
        `Ora a Roma: ${r.weekday} ${r.hour}:${String(r.minute).padStart(2, '0')}`,
        `Job disponibili: ${Object.keys(JOBS).join(', ')}`
      ].join('\n') + '\n');
    }
    if (sezione !== 'test' || !segreto(env.TEST_KEY) || chiave !== segreto(env.TEST_KEY) || !JOBS[job]) return new Response('Not found', { status: 404 });
    try {
      return new Response(await dispatch(env, job) + '\n');
    } catch (err) {
      return new Response(`ERRORE: ${err.message}\n`, { status: 502 });
    }
  }
};
