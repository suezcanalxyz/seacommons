# SPDX-License-Identifier: AGPL-3.0-or-later
"""Conservative security RSS/Atom intake. Evidence only, never auto-publish.

Feeds are configured by an operator in SEACOMMONS_SECURITY_RSS_FEEDS as JSON
list of {url,label,independence_group}. No unverified URLs are shipped.
"""
from __future__ import annotations
import hashlib
import ipaddress
import socket
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

_ATTACK = re.compile(r'\b(?:attacked?|struck|strikes?|drone attack|missile attack|torpedoed|explosion|hit by (?:a )?(?:drone|missile))\b',re.I)
_MARITIME = re.compile(r'\b(?:vessel|ship|tanker|cargo|container ship|merchant|maritime|shipping|port|sea|coast guard)\b',re.I)
_MMSI = re.compile(r'\bMMSI\s*[:#-]?\s*(\d{9})\b',re.I)
_IMO = re.compile(r'\bIMO\s*[:#-]?\s*(\d{7})\b',re.I)

def classify_security_report(title: str, description: str) -> dict | None:
    text=f'{title} {description}'
    # An area-wide risk bulletin is context, not a report of a ship attack.
    if re.search(r'\b(?:risk|threat|warning|advisory|potential|possible) of (?:an? )?(?:attack|strike)\b',text,re.I):
        return None
    # Require attack and maritime language in a bounded local context.
    attacks=list(_ATTACK.finditer(text))
    maritime=list(_MARITIME.finditer(text))
    if not any(abs(a.start()-m.start()) <= 130 for a in attacks for m in maritime):
        return None
    mmsi=_MMSI.search(text)
    imo=_IMO.search(text)
    return {'report_kind':'possible_maritime_attack','mmsi':mmsi.group(1) if mmsi else None,
            'imo':imo.group(1) if imo else None,'verification_status':'unverified_public_source',
            'publication_status':'private','requires_operator_review':True}

def configured_feeds() -> list[dict]:
    raw=os.environ.get('SEACOMMONS_SECURITY_RSS_FEEDS','[]')
    try:
        feeds=json.loads(raw)
    except (ValueError,TypeError):
        return []
    if not isinstance(feeds,list):
        return []
    valid=[]
    for feed in feeds:
        if not isinstance(feed,dict):continue
        url=str(feed.get('url',''))
        parsed=urlparse(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:continue
        if parsed.hostname == 'localhost' or parsed.hostname.endswith('.localhost'):
            continue
        try:
            address=ipaddress.ip_address(parsed.hostname)
            if not address.is_global:
                continue
        except ValueError:
            pass
        if not feed.get('label') or not feed.get('independence_group'):continue
        valid.append({'url':url,'label':str(feed['label']),
                      'independence_group':str(feed['independence_group'])})
    return valid

class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _public_dns(hostname: str) -> bool:
    """Reject internal address targets before connecting to configured sources."""
    try:
        answers=socket.getaddrinfo(hostname,443,type=socket.SOCK_STREAM)
        return bool(answers) and all(
            ipaddress.ip_address(a[4][0]).is_global for a in answers
        )
    except (OSError,ValueError):
        return False


def ingest_security_rss(*, fetch=None, record=None) -> dict:
    """Poll explicitly approved sources and preserve raw evidence, not incidents."""
    from core.intel.news_monitor import _parse_rss, _clean_rss_text, _parse_date, _HEADERS
    from core.intel.source_registry import source_registry
    from core.intel.source_observation import record_observation
    from core.intel.geoextract import extract_numeric_coords
    from core.db.session import session_scope
    feeds=configured_feeds()
    source_registry.register('Maritime Security RSS','rss')
    source_registry.register_targets('Maritime Security RSS',[f['label'] for f in feeds])
    total=0;errors=[]
    for feed in feeds:
        count=0
        try:
            if fetch is None:
                req=urllib.request.Request(feed['url'],headers=_HEADERS)
                if not _public_dns(urlparse(feed['url']).hostname):
                    raise ValueError('non-public feed address')
                with urllib.request.build_opener(_NoRedirects).open(req,timeout=12) as resp:
                    xml=resp.read(2_000_001).decode('utf-8',errors='replace')
                    if len(xml)>2_000_000:
                        raise ValueError('feed exceeds size limit')
            else: xml=fetch(feed['url'])
            for item in _parse_rss(xml):
                title=item.get('title',''); body=_clean_rss_text(item)
                classification=classify_security_report(title,body)
                if classification is None:continue
                key=item.get('guid') or item.get('link') or title
                source_id=hashlib.sha256(f"{feed['label']}:{key}".encode()).hexdigest()[:32]
                explicit_coords=extract_numeric_coords(f'{title} {body}')
                subject_refs=[]
                if classification.get('mmsi'):
                    subject_refs.append(f"subj:mmsi:{classification['mmsi']}")
                if classification.get('imo'):
                    subject_refs.append(f"subj:imo:{classification['imo']}")
                payload=json.dumps({'article':item,'classification':classification,
                                    'independence_group':feed['independence_group'],
                                    'publication_time_raw':item.get('pub_date',''),
                                    'received_at':datetime.now(timezone.utc).isoformat()},sort_keys=True)
                if record is not None:
                    record(feed,source_id,payload)
                else:
                    with session_scope() as db:
                        record_observation(db,service='maritime',lane='security',
                            observation_type='source_post',source_name=feed['label'],
                            source_policy='official_rss',source_id=source_id,
                            observed_at=_parse_date(item.get('pub_date','')),
                            raw_payload=payload,source_url=item.get('link',''),
                            lat=(explicit_coords[0] if explicit_coords else None),
                            lon=(explicit_coords[1] if explicit_coords else None),
                            location_precision=('explicit_text_coordinate' if explicit_coords else None),
                            subject_refs=subject_refs,
                            provenance={'independence_group':feed['independence_group'],
                                        'title':title[:300],
                                        'publication_time_raw':item.get('pub_date',''),
                                        'mmsi':classification.get('mmsi'),
                                        'imo':classification.get('imo'),
                                        'report_kind':classification.get('report_kind'),
                                        'event_time_basis':'publication_time_only',
                                        'requires_operator_review':True,
                                        'publication_allowed':False,
                                        'extraction_version':'attack_rss_candidate_v2'})
                count+=1;total+=1
            source_registry.record_target_poll('Maritime Security RSS',feed['label'],events_found=count)
        except Exception as exc:
            errors.append(f"{feed['label']}: {type(exc).__name__}")
            source_registry.record_target_poll('Maritime Security RSS',feed['label'],error=str(exc))
    source_registry.record_poll('Maritime Security RSS',events_found=total,
                                error='; '.join(errors) if feeds and len(errors)==len(feeds) else None)
    contexts={'scanned':0,'groups':0,'saved':0,'with_track_context':0}
    context_error=None
    if record is None and total:
        try:
            from core.intel.attack_pipeline import refresh_recent_attack_contexts
            contexts=refresh_recent_attack_contexts(limit=100)
        except Exception as exc:
            context_error=type(exc).__name__
    return {'observations':total,'feeds':len(feeds),'errors':errors,
            'correlation_contexts':contexts,'correlation_error':context_error}
