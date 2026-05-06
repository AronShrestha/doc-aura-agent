from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
import os

from aura_backend.models import AnalysisRun, DocSection, Artifact, ArtifactEdge

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./aura.db")
engine = create_async_engine(DATABASE_URL)
Session = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI(title="Aura MCP Read-only", version="0.1.0")


@app.get("/mcp/list_sections")
async def list_sections(repo_id: int):
    async with Session() as s:
        run = (await s.execute(select(AnalysisRun).where(AnalysisRun.repo_id == repo_id).order_by(AnalysisRun.id.desc()))).scalars().first()
        if not run:
            raise HTTPException(status_code=404, detail="repo_not_found")
        sections = (await s.execute(select(DocSection).where(DocSection.run_id == run.id))).scalars().all()
        return {"repo_id": repo_id, "run_id": run.id, "sections": [{"section_id": x.section_id, "title": x.title, "diataxis_type": x.diataxis_type} for x in sections]}


@app.get("/mcp/get_section")
async def get_section(repo_id: int, section_id: str):
    async with Session() as s:
        run = (await s.execute(select(AnalysisRun).where(AnalysisRun.repo_id == repo_id).order_by(AnalysisRun.id.desc()))).scalars().first()
        if not run:
            raise HTTPException(status_code=404, detail="repo_not_found")
        section = (await s.execute(select(DocSection).where(DocSection.run_id == run.id, DocSection.section_id == section_id))).scalars().first()
        if not section:
            raise HTTPException(status_code=404, detail="section_not_found")
        return {
            "section_id": section.section_id,
            "title": section.title,
            "diataxis_type": section.diataxis_type,
            "content_md": section.content_md,
            "provenance": section.provenance,
        }


@app.get("/mcp/search")
async def search(repo_id: int, query: str, top_k: int = 20):
    q = query.lower()
    async with Session() as s:
        run = (await s.execute(select(AnalysisRun).where(AnalysisRun.repo_id == repo_id).order_by(AnalysisRun.id.desc()))).scalars().first()
        if not run:
            raise HTTPException(status_code=404, detail="repo_not_found")
        sections = (await s.execute(select(DocSection).where(DocSection.run_id == run.id))).scalars().all()
        artifacts = (await s.execute(select(Artifact).where(Artifact.run_id == run.id))).scalars().all()
        hits = []
        for sec in sections:
            score = int(q in sec.title.lower()) * 2 + int(q in sec.content_md.lower())
            if score:
                hits.append({"kind": "section", "id": sec.section_id, "label": sec.title, "score": score})
        for art in artifacts:
            score = int(q in art.name.lower()) * 2 + int(q in str(art.payload).lower())
            if score:
                hits.append({"kind": "artifact", "id": art.artifact_id, "label": art.name, "score": score})
        hits.sort(key=lambda h: h["score"], reverse=True)
        return {"results": hits[:top_k]}


@app.get("/mcp/get_artifact")
async def get_artifact(repo_id: int, artifact_id: str):
    async with Session() as s:
        run = (await s.execute(select(AnalysisRun).where(AnalysisRun.repo_id == repo_id).order_by(AnalysisRun.id.desc()))).scalars().first()
        if not run:
            raise HTTPException(status_code=404, detail="repo_not_found")
        artifact = (await s.execute(select(Artifact).where(Artifact.run_id == run.id, Artifact.artifact_id == artifact_id))).scalars().first()
        if not artifact:
            raise HTTPException(status_code=404, detail="artifact_not_found")
        return {
            "artifact_id": artifact.artifact_id,
            "category": artifact.category,
            "name": artifact.name,
            "payload": artifact.payload,
            "provenance": [{"source_file": artifact.source_file, "source_line_start": artifact.source_line_start, "source_line_end": artifact.source_line_end, "confidence": 0.9}],
        }


@app.get("/mcp/get_dependencies")
async def get_dependencies(repo_id: int, artifact_id: str):
    async with Session() as s:
        run = (await s.execute(select(AnalysisRun).where(AnalysisRun.repo_id == repo_id).order_by(AnalysisRun.id.desc()))).scalars().first()
        if not run:
            raise HTTPException(status_code=404, detail="repo_not_found")
        deps = (await s.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == run.id, ArtifactEdge.src_artifact_id == artifact_id))).scalars().all()
        return {"artifact_id": artifact_id, "dependencies": [{"dst_artifact_id": d.dst_artifact_id, "kind": d.kind, "confidence": 0.9} for d in deps]}


@app.get("/mcp/get_run_summary")
async def get_run_summary(run_id: int):
    async with Session() as s:
        run = (await s.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalars().first()
        if not run:
            raise HTTPException(status_code=404, detail="run_not_found")
        return {
            "run_id": run.id,
            "repo_id": run.repo_id,
            "status": run.status,
            "stage": run.stage,
            "progress": run.progress,
            "quality_report": run.quality_report,
        }
