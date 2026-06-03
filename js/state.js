/* ═══ STATE ═══ */

const AV=['av0','av1','av2','av3','av4','av5'];
const SM={
  new:{l:'Da contattare',c:'bn'},sent:{l:'Email inviata',c:'bs'},
  followup:{l:'Follow-up',c:'bf'},replied:{l:'Risposto',c:'br'},
  client:{l:'Cliente',c:'bc'},cold:{l:'Non interessato',c:'bx'}
};
const PRODS=['Rosso','Bianco','Rosé','Bollicine/Spumante','Prosecco','Barolo','Brunello','Amarone',
  'Primitivo',"Nero d'Avola",'Vermentino','Pinot Grigio','Organic/Bio','Natural Wine','Orange Wine','Grappa/Distillati'];
const CLIST=['Germania','USA','UK','Svizzera','Austria','Belgio','Paesi Bassi','Canada','Australia',
  'Giappone','Cina','Svezia','Norvegia','Danimarca','Brasile','Messico','Singapore','Hong Kong',
  'Francia','Spagna','Polonia','Rep. Ceca','Emirati Arabi','Corea del Sud'];

let db={contacts:[],templates:[]};     // importatori
let dbC={contacts:[],templates:[]};    // clienti privati
let dbO={orders:[],lastImportedAt:null}; // ordini
let dbRemT={};                         // template email reminder
let layer='importatori';               // layer attivo
let ghs={};
let brv={};
let sel=new Set();
let regSel=new Set();
let _pendingEmailId=null; // id contatto per apertura email da scheda
let ghSha={importatori:null,clienti:null,templates:null,ordini:null,reminders:null};
let saveTimer=null,saveOrdTimer=null,pending=null;