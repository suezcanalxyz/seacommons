import React,{createContext,useContext} from 'react';
import it from './locale.it.json';
const LocaleContext=createContext('en');
export const FuturesLocale=LocaleContext.Provider;
export function useLocale(){return useContext(LocaleContext);}
export function translate(value,lang){
 if(lang!=='it'||typeof value!=='string')return value;
 const key=value.trim().replace(/\s+/g,' ');
 const result=it[key];
 if(typeof result!=='string'||!Object.prototype.hasOwnProperty.call(it,key))return value;
 return (value.match(/^\s*/)?.[0]||'')+result+(value.match(/\s*$/)?.[0]||'');
}
export function useT(){const lang=useLocale();return value=>translate(value,lang);}
export function L({children}){const t=useT();return typeof children==='string'?t(children):children;}
export function useFormat(){const lang=useLocale();const loc=lang==='it'?'it-IT':'en-GB';return {number:n=>new Intl.NumberFormat(loc).format(n),date:d=>new Intl.DateTimeFormat(loc,{dateStyle:'medium',timeStyle:'short'}).format(new Date(d))};}
