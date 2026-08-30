"""Offline, privacy-bounded Engram vector retrieval experiment."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import argparse, hashlib, json, os, tempfile
from pathlib import Path
from typing import Any

from engram import EmbeddingService, ProjectMemory, Telemetry
from llm_harness_core import Actor, CapabilityClaim, CapabilityRequirement, DeterminismClaim, PrivacyDeclaration, PrivacyValidation, RecordEnvelope, RunArtifact, TimeDeclaration, TimeValue, dump_artifact

PROFILE = "examples.engram_vector_retrieval"

@dataclass(frozen=True)
class Memory:
    memory_id: str; role: str; text: str

@dataclass(frozen=True)
class Case:
    case_id: str; query: str; relevant_id: str; conflict_id: str; memories: tuple[Memory, ...]

def cases() -> tuple[Case, ...]:
    rows = (
      ("orion_geo", "Which European cloud geography should Orion workloads use?", "VM-ORION-R", "VM-ORION-C", "Frankfurt Germany eu-central-1 is the current authoritative location for Orion application deployment.", "An obsolete Orion draft selected Oregon us-west-2 and is superseded.", "Orion latency tests compare several European zones.", "Payroll reports are delivered every second Friday."),
      ("lumen_retention", "How long must Lumen audit material be preserved?", "VM-LUMEN-R", "VM-LUMEN-C", "The current Lumen audit preservation duration is forty-five days.", "A superseded Lumen policy retained audit material for ninety days.", "Lumen audit exports are encrypted before transfer.", "The cafeteria closes at six in the evening."),
      ("cedar_owner", "Who receives urgent Cedar incident escalations?", "VM-CEDAR-R", "VM-CEDAR-C", "Urgent Cedar incidents currently route to the ORANGE response team.", "The old BLUE team assignment for Cedar was superseded.", "Cedar incident dashboards display severity and age.", "Building access badges expire annually."),
      ("delta_time", "At what UTC time does Delta maintenance begin?", "VM-DELTA-R", "VM-DELTA-C", "Delta's authoritative maintenance start is half past three UTC.", "A retired Delta schedule began maintenance at 01:00 UTC.", "Delta maintenance requires a change ticket.", "Conference rooms can be booked online."),
      ("ember_encoding", "What file representation is required for Ember exports?", "VM-EMBER-R", "VM-EMBER-C", "Current Ember exports must use the Apache Parquet columnar representation.", "The superseded Ember export draft required comma-separated CSV files.", "Ember export jobs run after validation completes.", "Office printers default to double-sided output."),
    )
    out=[]
    for cid,q,r,c,rt,ct,nt,it in rows:
        out.append(Case(cid,q,r,c,(Memory(r,"relevant",rt),Memory(c,"conflict",ct),Memory(r.replace("-R","-N"),"near",nt),Memory(r.replace("-R","-I"),"irrelevant",it))))
    return tuple(out)

def suite_digest() -> str:
    return "sha256:"+hashlib.sha256(json.dumps([asdict(c) for c in cases()],sort_keys=True,separators=(",",":")).encode()).hexdigest()

def _run_condition(case: Case, root: Path, embedder: Any | None) -> dict[str,Any]:
    events=[]; telemetry=Telemetry(); telemetry.add_sink(events.append)
    mem=ProjectMemory(base_dir=root,project_id=case.case_id,session_id="probe",embedder=embedder,telemetry=telemetry,enable_semantic_graph=False)
    try:
        for item in case.memories:
            mem.store_episode(item.text,{"memory_id":item.memory_id,"role":item.role},importance=1.0 if item.role=="relevant" else .8,bypass_filter=True)
        hits=mem.search_episodes(case.query,n=3)
        ids=[getattr(h,"metadata",{}).get("memory_id") for h in hits]
        scores=[round(float(getattr(h,"score",0.0)),8) for h in hits]
        search=next(e.data for e in reversed(events) if e.event_type=="search_completed")
        return {"ranked_ids":ids,"scores":scores,"vector_search_used":bool(search["used_vector_search"]),"vector_filtered_count":search["vector_filtered_count"],"relevant_recalled":case.relevant_id in ids,"relevant_ahead_of_conflict":case.relevant_id in ids and (case.conflict_id not in ids or ids.index(case.relevant_id)<ids.index(case.conflict_id)),"stored_count":len(case.memories),"chroma_count":mem.chromadb.count() if mem.chromadb else None}
    finally: mem.close()

def run(root: Path) -> dict[str,Any]:
    started=datetime.now(timezone.utc); observations=[]
    for case in cases(): observations.append({"case_id":case.case_id,"condition":"text_only",**_run_condition(case,root/"text"/case.case_id,None)})
    embedder=EmbeddingService.sentence_transformers(model="all-MiniLM-L6-v2",device="cpu")
    for case in cases(): observations.append({"case_id":case.case_id,"condition":"hybrid",**_run_condition(case,root/"hybrid"/case.case_id,embedder)})
    hybrid=[o for o in observations if o["condition"]=="hybrid"]
    finished=datetime.now(timezone.utc)
    return {"schema_version":1,"profile":PROFILE,"profile_version":1,"suite_digest":suite_digest(),"started_at":started.isoformat().replace("+00:00","Z"),"finished_at":finished.isoformat().replace("+00:00","Z"),"embedder_label":"sentence-transformers/all-MiniLM-L6-v2","embedding_dimension":384,"condition_order":"all_text_only_then_all_hybrid","case_count":5,"hybrid_vector_used_count":sum(o["vector_search_used"] for o in hybrid),"hybrid_relevant_recall_count":sum(o["relevant_recalled"] for o in hybrid),"hybrid_relevant_ahead_count":sum(o["relevant_ahead_of_conflict"] for o in hybrid),"observations":observations,"interpretation_limit":"Five fixed synthetic cases; not a general retrieval-quality estimate."}

def artifact(body:dict[str,Any])->RunArtifact:
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return RunArtifact(RecordEnvelope(kind="experiment",envelope_schema_version=1,body_version=1,profile=PROFILE,profile_version=1,record_id=f"vr_{digest[:32]}",lifecycle="final",relationships=(),attachments=(),actors=(Actor("vector-memory-runner","recorder",PROFILE,"1"),),time=TimeDeclaration(TimeValue("value",body["started_at"],"runner"),TimeValue("value",body["finished_at"],"runner"),TimeValue("value",body["finished_at"],"runner")),privacy=PrivacyDeclaration(declared_content_categories=("synthetic_memory",),body_bytes_sensitivity="low; raw synthetic text omitted",transformations_applied=({"operation":"retain_ids_and_scores_only","version":"1"},),validation=PrivacyValidation("validated",("no raw query or memory text",),PROFILE,"synthetic-only","1",body["finished_at"])),capabilities=(CapabilityClaim("vector_memory_retrieval",(CapabilityRequirement("implementation","engram"),CapabilityRequirement("implementation","chromadb"),CapabilityRequirement("model","all-MiniLM-L6-v2")),"local_compute","state_changing",DeterminismClaim("best_effort","exercised",("cached model","cpu")),"1"),),execution_environment={"embedder_label":body["embedder_label"]}),body)

def main(argv=None)->int:
    p=argparse.ArgumentParser();p.add_argument("--artifact",type=Path,required=True);a=p.parse_args(argv)
    a.artifact.parent.mkdir(parents=True,exist_ok=True)
    if a.artifact.exists():p.error(f"artifact already exists: {a.artifact}")
    with tempfile.TemporaryFile(dir=a.artifact.parent):pass
    os.environ.setdefault("HF_HUB_OFFLINE","1");os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
    with tempfile.TemporaryDirectory(prefix="vector-memory-") as t: body=run(Path(t))
    dump_artifact(artifact(body),a.artifact);print(json.dumps({k:v for k,v in body.items() if k!="observations"},indent=2,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
