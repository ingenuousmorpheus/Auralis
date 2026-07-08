import React, { useEffect, useRef, useState } from "react";
import VocalRack from "./VocalRack.jsx";

export default function VoiceStudio({API, card, btn, colors, onBack}) {
  const {V,T,PK,PANEL2,TEXT,MUTE} = colors;
  const [provider,setProvider] = useState(null);
  const [profiles,setProfiles] = useState([]);
  const [name,setName] = useState("My Singing Voice");
  const [reference,setReference] = useState(null);
  const [datasetFiles,setDatasetFiles] = useState([]);
  const [pairedGuide,setPairedGuide] = useState(null);
  const [pairedSinger,setPairedSinger] = useState(null);
  const [consent,setConsent] = useState(false);
  const [selected,setSelected] = useState("");
  const [guide,setGuide] = useState(null);
  const [quality,setQuality] = useState("studio");
  const [shift,setShift] = useState(0);
  const [trainingDepth,setTrainingDepth] = useState("studio");
  const [trainingDetails,setTrainingDetails] = useState(null);
  const [busy,setBusy] = useState(false);
  const [stage,setStage] = useState("");
  const [pct,setPct] = useState(0);
  const [jobId,setJobId] = useState(null);
  const [result,setResult] = useState(null);
  const [showFinish,setShowFinish] = useState(false);
  const [pitchStyle,setPitchStyle] = useState("studio");
  const [pitchKey,setPitchKey] = useState("auto");
  const [pitchInstrumental,setPitchInstrumental] = useState(null);
  const [pitchJobId,setPitchJobId] = useState(null);
  const [pitchResult,setPitchResult] = useState(null);
  const [showPitch,setShowPitch] = useState(false);
  const [autoInstrumental,setAutoInstrumental] = useState(null);
  const [autoJobId,setAutoJobId] = useState(null);
  const [autoResult,setAutoResult] = useState(null);
  const [error,setError] = useState("");
  const referenceInput = useRef();
  const datasetInput = useRef();
  const pairedGuideInput = useRef();
  const pairedSingerInput = useRef();
  const guideInput = useRef();
  const pitchInstrumentalInput = useRef();
  const autoInstrumentalInput = useRef();

  async function apiJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  async function refresh() {
    const [engine,voices] = await Promise.all([
      apiJson(`${API}/voice/provider`),
      apiJson(`${API}/voice/profiles`),
    ]);
    setProvider(engine); setProfiles(voices);
    if(!selected && voices.length) setSelected(voices[0].id);
  }

  useEffect(()=>{ refresh().catch(e=>setError(e.message)); },[]);

  function watchJob(id, done, assignResult=true) {
    const ws = new WebSocket(`${API.replace("http","ws")}/ws/jobs/${id}`);
    ws.onmessage = event => {
      const data = JSON.parse(event.data);
      setStage(data.stage || ""); setPct(data.pct || 0);
      setTrainingDetails(data.details || null);
      if(data.stage==="error") {
        setError(data.error || "The voice job failed."); setBusy(false);
      }
      if(data.stage==="done") {
        setBusy(false); if(assignResult) setResult(data.result); if(done) done(data.result);
      }
    };
    ws.onerror = ()=>{ setError("Lost connection to the local voice worker."); setBusy(false); };
  }

  async function installEngine() {
    setError(""); setBusy(true); setStage("preparing install"); setPct(0);
    try {
      const data = await apiJson(`${API}/voice/provider/install`,{method:"POST"});
      setJobId(data.job_id);
      watchJob(data.job_id, ()=>refresh().catch(e=>setError(e.message)));
    } catch(e) { setError(e.message); setBusy(false); }
  }

  async function createProfile() {
    if(!reference) return;
    setError(""); setBusy(true); setStage("preparing voice reference");
    try {
      const form = new FormData();
      form.append("name",name);
      form.append("consent_confirmed",String(consent));
      form.append("file",reference);
      const profile = await apiJson(`${API}/voice/profiles`,{method:"POST",body:form});
      setSelected(profile.id); setReference(null); setConsent(false);
      await refresh();
    } catch(e) { setError(e.message); }
    finally { setBusy(false); setStage(""); }
  }

  async function convert() {
    if(!guide || !selected) return;
    setError(""); setResult(null); setPitchResult(null); setAutoResult(null);
    setShowPitch(false); setShowFinish(false);
    setBusy(true); setStage("uploading guide vocal"); setPct(0);
    try {
      const form = new FormData();
      form.append("profile_id",selected);
      form.append("semitone_shift",String(shift));
      form.append("quality",quality);
      form.append("file",guide);
      const data = await apiJson(`${API}/voice/convert`,{method:"POST",body:form});
      setJobId(data.job_id); watchJob(data.job_id);
    } catch(e) { setError(e.message); setBusy(false); }
  }

  async function autoStudioPolish() {
    if(!jobId || !result?.output_path) return;
    setError(""); setAutoResult(null); setBusy(true); setStage("starting one-click studio polish"); setPct(0);
    try {
      const form = new FormData();
      form.append("source_job_id",jobId);
      if(autoInstrumental) form.append("instrumental",autoInstrumental);
      const data = await apiJson(`${API}/voice/auto-polish`,{method:"POST",body:form});
      setAutoJobId(data.job_id);
      watchJob(data.job_id,(polished)=>setAutoResult(polished),false);
    } catch(e) { setError(e.message); setBusy(false); }
  }

  async function polishPitch() {
    if(!jobId || !result?.output_path) return;
    setError(""); setPitchResult(null);
    setBusy(true); setStage("detecting key and melody"); setPct(0);
    try {
      const form = new FormData();
      form.append("source_job_id",jobId);
      form.append("style",pitchStyle);
      form.append("key",pitchKey);
      if(pitchInstrumental) form.append("instrumental",pitchInstrumental);
      const data = await apiJson(`${API}/voice/pitch`,{method:"POST",body:form});
      setPitchJobId(data.job_id);
      watchJob(data.job_id,(polished)=>setPitchResult(polished),false);
    } catch(e) { setError(e.message); setBusy(false); }
  }

  async function addDataset() {
    if(!selected || !datasetFiles.length) return;
    setError(""); setBusy(true); setStage("cleaning and segmenting recordings"); setPct(5);
    try {
      const form = new FormData();
      datasetFiles.forEach(file=>form.append("files",file));
      await apiJson(`${API}/voice/profiles/${selected}/recordings`,{method:"POST",body:form});
      setDatasetFiles([]); await refresh();
    } catch(e) { setError(e.message); }
    finally { setBusy(false); setStage(""); setPct(0); }
  }

  async function trainStudio() {
    if(!selected) return;
    setError(""); setResult(null); setBusy(true); setStage("queuing studio voice"); setPct(0);
    try {
      const data = await apiJson(`${API}/voice/train`,{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({profile_id:selected,depth:trainingDepth}),
      });
      setJobId(data.job_id);
      watchJob(data.job_id,()=>refresh().catch(e=>setError(e.message)));
    } catch(e) { setError(e.message); setBusy(false); }
  }

  async function addPairedCalibration() {
    if(!selected||!pairedGuide||!pairedSinger) return;
    setError(""); setBusy(true); setStage("aligning guide and real performance"); setPct(8);
    try {
      const form = new FormData();
      form.append("name",`${pairedGuide.name} paired calibration`);
      form.append("guide",pairedGuide);
      form.append("singer",pairedSinger);
      await apiJson(`${API}/voice/profiles/${selected}/paired-calibration`,{method:"POST",body:form});
      setPairedGuide(null); setPairedSinger(null); await refresh();
    } catch(e) { setError(e.message); }
    finally { setBusy(false); setStage(""); setPct(0); }
  }

  const choice = active => ({
    flex:1,padding:"9px 5px",borderRadius:9,border:"none",cursor:"pointer",
    background:active?"#222842":PANEL2,color:active?T:MUTE,fontWeight:700,fontSize:12,
  });
  const selectedProfile = profiles.find(p=>p.id===selected);
  const minutes = ((selectedProfile?.dataset_duration_seconds||0)/60).toFixed(1);
  const pitchSpan = selectedProfile?.pitch_low_midi!=null && selectedProfile?.pitch_high_midi!=null
    ? Math.round(selectedProfile.pitch_high_midi-selectedProfile.pitch_low_midi) : 0;

  return <div className="voice-command-center">
    <button style={{...btn(false),marginTop:0}} onClick={onBack}>← Auralis home</button>
    <h2 style={{marginBottom:4}}>My Voice Studio</h2>
    <p style={{color:MUTE,fontSize:13,marginTop:0}}>
      Convert a dry guide vocal into your singing timbre while preserving its melody and timing.
    </p>

    {error && <div style={{...card,background:"#2a1620",color:PK,marginBottom:12,fontSize:12}}>{error}</div>}

    <div style={{...card,marginBottom:12,border:`1px solid ${provider?.installed?T+"66":V+"55"}`}}>
      <div style={{display:"flex",alignItems:"center",gap:10}}>
        <div style={{fontSize:22}}>{provider?.installed?"✓":"⚙"}</div>
        <div style={{flex:1}}>
          <b style={{fontSize:14}}>Local singing engine</b>
          <div style={{fontSize:11,color:MUTE,marginTop:3}}>
            {provider?.installed?"Seed-VC is installed and GPU-ready.":"One-time isolated install. Model files stay on this PC."}
          </div>
        </div>
      </div>
      {!provider?.installed && <button disabled={busy} style={{...btn(true),opacity:busy?.6:1}} onClick={installEngine}>
        Install Voice Engine
      </button>}
    </div>

    <div style={{...card,marginBottom:12}}>
      <b style={{fontSize:14}}>1. Create your private voice profile</b>
      <p style={{fontSize:11,color:MUTE,lineHeight:1.5}}>
        Use 3–30 seconds of dry solo singing: no beat, harmony, reverb, tuning artifacts, or clipping.
      </p>
      <input value={name} onChange={e=>setName(e.target.value)}
        style={{width:"100%",boxSizing:"border-box",background:"#0d1019",border:"1px solid #2a3050",
          color:TEXT,padding:11,borderRadius:9,marginBottom:9}}/>
      <div onClick={()=>referenceInput.current.click()} style={{padding:16,textAlign:"center",
        border:"1px dashed #303758",borderRadius:10,cursor:"pointer",fontSize:12,color:reference?T:MUTE}}>
        {reference?reference.name:"Choose clean voice reference"}
      </div>
      <input ref={referenceInput} type="file" accept="audio/*" style={{display:"none"}}
        onChange={e=>setReference(e.target.files[0]||null)}/>
      <label style={{display:"flex",gap:8,alignItems:"flex-start",fontSize:11,color:MUTE,marginTop:10}}>
        <input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>
        I confirm this is my voice, or I have the singer's explicit permission to create and use this profile.
      </label>
      <button disabled={!reference||!consent||busy} onClick={createProfile}
        style={{...btn(false),opacity:reference&&consent&&!busy?1:.4}}>Create Voice Profile</button>
    </div>

    <div style={{...card,marginBottom:12}}>
      <b style={{fontSize:14}}>2. Build a full Studio Voice</b>
      {profiles.length===0 ? <p style={{fontSize:12,color:MUTE}}>Create a profile above first.</p> :
        <select value={selected} onChange={e=>setSelected(e.target.value)}
          style={{width:"100%",marginTop:10,background:"#0d1019",border:"1px solid #2a3050",
            color:TEXT,padding:11,borderRadius:9}}>
          {profiles.map(p=><option key={p.id} value={p.id}>
            {p.name} · {p.kind==="studio-trained"?"Studio trained":"Instant"}
          </option>)}
        </select>}
      <p style={{fontSize:11,color:MUTE,lineHeight:1.5}}>
        Add 30–45 minutes covering low, middle, high, soft, powerful, sustained, rhythmic, and breathy singing.
        Auralis will split long takes into clean training phrases.
      </p>
      <div onClick={()=>datasetInput.current.click()} style={{padding:16,textAlign:"center",
        border:"1px dashed #303758",borderRadius:10,cursor:"pointer",fontSize:12,
        color:datasetFiles.length?T:MUTE}}>
        {datasetFiles.length?`${datasetFiles.length} recording${datasetFiles.length===1?"":"s"} selected`
          :"Choose multiple dry vocal recordings"}
      </div>
      <input ref={datasetInput} type="file" accept="audio/*" multiple style={{display:"none"}}
        onChange={e=>setDatasetFiles(Array.from(e.target.files||[]))}/>
      <button disabled={!selected||!datasetFiles.length||busy} onClick={addDataset}
        style={{...btn(false),opacity:selected&&datasetFiles.length&&!busy?1:.4}}>Analyze + Add Recordings</button>

      <div style={{marginTop:12,padding:12,borderRadius:10,background:"#111522",border:"1px solid #29304b"}}>
        <b style={{fontSize:12}}>Paired Calibration</b>
        <div style={{fontSize:10,color:MUTE,lineHeight:1.45,marginTop:4}}>
          Add an AI guide vocal and your matching performance. Auralis rejects mismatched
          songs and keeps only strongly aligned phrases.
        </div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:7,marginTop:9}}>
          <div onClick={()=>pairedGuideInput.current.click()} style={{padding:10,textAlign:"center",
            border:"1px dashed #303758",borderRadius:8,cursor:"pointer",fontSize:10,
            color:pairedGuide?T:MUTE}}>{pairedGuide?pairedGuide.name:"AI guide vocal"}</div>
          <div onClick={()=>pairedSingerInput.current.click()} style={{padding:10,textAlign:"center",
            border:"1px dashed #303758",borderRadius:8,cursor:"pointer",fontSize:10,
            color:pairedSinger?T:MUTE}}>{pairedSinger?pairedSinger.name:"My matching vocal"}</div>
        </div>
        <input ref={pairedGuideInput} type="file" accept="audio/*" style={{display:"none"}}
          onChange={e=>setPairedGuide(e.target.files[0]||null)}/>
        <input ref={pairedSingerInput} type="file" accept="audio/*" style={{display:"none"}}
          onChange={e=>setPairedSinger(e.target.files[0]||null)}/>
        <button disabled={!selected||!pairedGuide||!pairedSinger||busy} onClick={addPairedCalibration}
          style={{...btn(false),opacity:selected&&pairedGuide&&pairedSinger&&!busy?1:.4}}>
          Align + Add Verified Pair
        </button>
      </div>

      {selectedProfile && <div style={{marginTop:12,padding:12,borderRadius:10,background:"#0d1019"}}>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:12}}>
          <span style={{color:MUTE}}>Studio readiness</span>
          <b style={{color:selectedProfile.readiness_score>=80?T:PK}}>{selectedProfile.readiness_score||0}%</b>
        </div>
        <div style={{height:6,background:"#191d2b",borderRadius:4,overflow:"hidden",margin:"8px 0"}}>
          <div style={{width:`${selectedProfile.readiness_score||0}%`,height:"100%",
            background:`linear-gradient(90deg,${V},${T})`}}/>
        </div>
        <div style={{fontSize:10,color:MUTE}}>
          {minutes} min · {selectedProfile.dataset_clip_count||0} phrases · {pitchSpan} semitone range
        </div>
        {(selectedProfile.paired_calibration_count||0)>0 && <div style={{fontSize:10,color:T,marginTop:5}}>
          {selectedProfile.paired_calibration_count} verified pair{selectedProfile.paired_calibration_count===1?"":"s"}
          {" · "}{Math.round(selectedProfile.paired_calibration_seconds||0)} aligned seconds
        </div>}
        {(selectedProfile.readiness_notes||[]).map(note=>
          <div key={note} style={{fontSize:10,color:"#b0b5cf",marginTop:5}}>• {note}</div>)}
        {selectedProfile.kind==="studio-trained" &&
          <div style={{fontSize:11,color:T,marginTop:8}}>✓ Studio model trained for {selectedProfile.training_steps} steps</div>}
      </div>}

      <div style={{fontSize:11,color:MUTE,marginTop:12,marginBottom:6}}>Training depth</div>
      <div style={{display:"flex",gap:7}}>
        <button onClick={()=>setTrainingDepth("studio")} style={choice(trainingDepth==="studio")}>
          Studio · 1,000
        </button>
        <button onClick={()=>setTrainingDepth("deep")} style={choice(trainingDepth==="deep")}>
          Deep · 2,500
        </button>
      </div>
      <button disabled={!provider?.installed||(selectedProfile?.dataset_duration_seconds||0)<600||busy}
        onClick={trainStudio} style={{...btn(true),
          opacity:provider?.installed&&(selectedProfile?.dataset_duration_seconds||0)>=600&&!busy?1:.4}}>
        {selectedProfile?.kind==="studio-trained"?"Continue / Deepen Training":"Train My Full Voice Profile"}
      </button>
    </div>

    <div style={card}>
      <b style={{fontSize:14}}>3. Convert a guide vocal</b>
      {selectedProfile && <div style={{fontSize:11,color:selectedProfile.kind==="studio-trained"?T:MUTE,marginTop:6}}>
        Using: {selectedProfile.kind==="studio-trained"?"full Studio Voice checkpoint":"instant reference voice"}
      </div>}
      <div onClick={()=>guideInput.current.click()} style={{padding:18,textAlign:"center",marginTop:10,
        border:"1px dashed #303758",borderRadius:10,cursor:"pointer",fontSize:12,color:guide?T:MUTE}}>
        {guide?guide.name:"Choose dry guide vocal"}
      </div>
      <input ref={guideInput} type="file" accept="audio/*" style={{display:"none"}}
        onChange={e=>setGuide(e.target.files[0]||null)}/>

      <div style={{fontSize:11,color:MUTE,marginTop:12,marginBottom:6}}>Render quality</div>
      <div style={{display:"flex",gap:7}}>
        {["fast","studio","ultra"].map(q=><button key={q} onClick={()=>setQuality(q)}
          style={choice(quality===q)}>{q}</button>)}
      </div>
      <div style={{display:"flex",justifyContent:"space-between",fontSize:11,color:MUTE,marginTop:13}}>
        <span>Pitch shift</span><b style={{color:T}}>{shift>0?"+":""}{shift} semitones</b>
      </div>
      <input type="range" min="-12" max="12" value={shift} onChange={e=>setShift(Number(e.target.value))}
        style={{width:"100%",accentColor:T}}/>
      <button disabled={!provider?.installed||!guide||!selected||busy} onClick={convert}
        style={{...btn(true),opacity:provider?.installed&&guide&&selected&&!busy?1:.4}}>
        Convert Into My Voice
      </button>
    </div>

    {busy && <div style={{...card,marginTop:12,textAlign:"center"}}>
      <div style={{fontSize:13,color:T,textTransform:"capitalize"}}>{stage}</div>
      <div style={{height:7,background:"#0c0e16",borderRadius:5,overflow:"hidden",marginTop:12}}>
        <div style={{width:`${pct}%`,height:"100%",background:`linear-gradient(90deg,${V},${T})`}}/>
      </div>
      <div style={{fontSize:10,color:MUTE,marginTop:7}}>
        {stage.includes("install")?"The first install can take several minutes.":
          stage.includes("training") && trainingDetails
            ? `Step ${trainingDetails.step||0} / ${trainingDetails.max_steps||0}${trainingDetails.loss!=null?` · loss ${Number(trainingDetails.loss).toFixed(4)}`:""}`
            :"Your audio remains on this computer."}
      </div>
    </div>}

    {result?.output_path && <div style={{...card,marginTop:12}}>
      <b style={{fontSize:14}}>Converted vocal ready</b>
      <div style={{fontSize:11,color:MUTE,marginTop:4}}>
        {result.profile_name} · {result.quality} · {result.semitone_shift>0?"+":""}{result.semitone_shift} semitones
      </div>
      <audio controls src={`${API}/voice/download/${jobId}`} style={{width:"100%",marginTop:12}}/>
      <a href={`${API}/voice/download/${jobId}`} style={{...btn(true),display:"block",
        textAlign:"center",textDecoration:"none"}}>Download Converted WAV</a>
      <div style={{marginTop:12,padding:12,borderRadius:10,background:"#0d1019",border:`1px solid ${T}44`}}>
        <b style={{fontSize:13,color:T}}>One-Click Studio Polish</b>
        <div style={{fontSize:10,color:MUTE,marginTop:4,lineHeight:1.4}}>
          Detect key → correct notes naturally → de-ess → serial compress → place in the beat.
        </div>
        <div onClick={()=>autoInstrumentalInput.current.click()} style={{padding:11,textAlign:"center",
          border:"1px dashed #303758",borderRadius:8,cursor:"pointer",fontSize:10,
          color:autoInstrumental?T:MUTE,marginTop:9}}>
          {autoInstrumental?`Instrumental: ${autoInstrumental.name}`:
            "Add instrumental for best results (recommended)"}
        </div>
        <input ref={autoInstrumentalInput} type="file" accept="audio/*" style={{display:"none"}}
          onChange={e=>setAutoInstrumental(e.target.files[0]||null)}/>
        <button disabled={busy} onClick={autoStudioPolish}
          style={{...btn(true),marginTop:8,opacity:busy?0.45:1}}>Polish Everything Automatically</button>
      </div>
      <button onClick={()=>setShowPitch(v=>!v)} style={{...btn(false),border:`1px solid ${T}55`}}>
        {showPitch?"Hide Pitch Polish":"Auto Pitch Polish →"}
      </button>
      <button onClick={()=>setShowFinish(v=>!v)} style={btn(false)}>
        {showFinish?"Hide Vocal Chain Rack":"Open Vocal Chain Rack →"}
      </button>
    </div>}

    {autoResult?.output_path && <div style={{...card,marginTop:12,border:`1px solid ${T}66`}}>
      <b style={{fontSize:15}}>Studio-polished vocal ready</b>
      <div style={{fontSize:11,color:T,marginTop:4}}>
        {autoResult.pitch?.key?.name} · {autoResult.pitch?.notes_corrected}/{autoResult.pitch?.notes_detected} notes corrected
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginTop:12}}>
        <div>
          <div style={{fontSize:10,color:MUTE,marginBottom:4}}>Before</div>
          <audio controls src={`${API}/voice/download/${jobId}`} style={{width:"100%"}}/>
        </div>
        <div>
          <div style={{fontSize:10,color:T,marginBottom:4}}>Fully polished</div>
          <audio controls src={`${API}/voice/auto-polish/${autoJobId}/download`} style={{width:"100%"}}/>
        </div>
      </div>
      {autoResult.preview_path && <>
        <div style={{fontSize:10,color:MUTE,marginTop:12,marginBottom:4}}>Inside the instrumental</div>
        <audio controls src={`${API}/voice/auto-polish/${autoJobId}/preview`} style={{width:"100%"}}/>
      </>}
      <a href={`${API}/voice/auto-polish/${autoJobId}/download`} style={{...btn(true),display:"block",
        textAlign:"center",textDecoration:"none"}}>Download Studio-Polished WAV</a>
    </div>}

    {result?.output_path && showPitch && <div style={{...card,marginTop:12,border:`1px solid ${T}55`}}>
      <b style={{fontSize:15}}>Pitch Polish</b>
      <p style={{fontSize:11,color:MUTE,lineHeight:1.5}}>
        Automatically detect the key and melody, then correct note centers while
        preserving vibrato, slides, breaths, and consonants. Add the instrumental
        for more reliable key detection.
      </p>
      <div style={{fontSize:11,color:MUTE,marginBottom:6}}>Correction character</div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:7}}>
        {[["natural","Natural"],["studio","Studio"],["modern","Modern"],["hard","Hard Tune"]]
          .map(([id,label])=><button key={id} onClick={()=>setPitchStyle(id)}
            style={choice(pitchStyle===id)}>{label}</button>)}
      </div>
      <div style={{fontSize:11,color:MUTE,marginTop:12,marginBottom:6}}>Song key</div>
      <select value={pitchKey} onChange={e=>setPitchKey(e.target.value)}
        style={{width:"100%",background:"#0d1019",border:"1px solid #2a3050",
          color:TEXT,padding:11,borderRadius:9}}>
        <option value="auto">Auto detect</option>
        {["C","C#","D","Eb","E","F","F#","G","Ab","A","Bb","B"].flatMap(note=>
          ["major","minor"].map(mode=>
            <option key={`${note} ${mode}`} value={`${note} ${mode}`}>{note} {mode}</option>))}
      </select>
      <div onClick={()=>pitchInstrumentalInput.current.click()} style={{padding:14,textAlign:"center",
        border:"1px dashed #303758",borderRadius:10,cursor:"pointer",fontSize:11,
        color:pitchInstrumental?T:MUTE,marginTop:10}}>
        {pitchInstrumental?`Key reference: ${pitchInstrumental.name}`:
          "Add instrumental for better key detection (recommended)"}
      </div>
      <input ref={pitchInstrumentalInput} type="file" accept="audio/*" style={{display:"none"}}
        onChange={e=>setPitchInstrumental(e.target.files[0]||null)}/>
      <button disabled={busy} onClick={polishPitch}
        style={{...btn(true),opacity:busy?0.45:1}}>Detect Key + Polish Notes</button>
    </div>}

    {pitchResult?.output_path && <div style={{...card,marginTop:12}}>
      <b style={{fontSize:15}}>Pitch-polished vocal ready</b>
      <div style={{fontSize:11,color:T,marginTop:4}}>
        {pitchResult.key?.name} · {pitchResult.style} · {pitchResult.notes_corrected}/{pitchResult.notes_detected} notes adjusted
      </div>
      <div style={{fontSize:10,color:MUTE,marginTop:5}}>
        Key confidence {Math.round((pitchResult.key?.confidence||0)*100)}% · average correction {pitchResult.average_correction_cents} cents
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginTop:12}}>
        <div>
          <div style={{fontSize:10,color:MUTE,marginBottom:4}}>Converted</div>
          <audio controls src={`${API}/voice/download/${jobId}`} style={{width:"100%"}}/>
        </div>
        <div>
          <div style={{fontSize:10,color:T,marginBottom:4}}>Pitch polished</div>
          <audio controls src={`${API}/voice/pitch/${pitchJobId}/download`} style={{width:"100%"}}/>
        </div>
      </div>
      {pitchResult.low_confidence_notes>0 && <div style={{fontSize:10,color:PK,marginTop:8}}>
        {pitchResult.low_confidence_notes} ambiguous note{pitchResult.low_confidence_notes===1?"":"s"} received restrained correction.
      </div>}
      <a href={`${API}/voice/pitch/${pitchJobId}/download`} style={{...btn(true),display:"block",
        textAlign:"center",textDecoration:"none"}}>Download Pitch-Polished WAV</a>
      <a href={`${API}/voice/pitch/${pitchJobId}/report`} style={{...btn(false),display:"block",
        textAlign:"center",textDecoration:"none",fontSize:12}}>Download Note Edit Report</a>
    </div>}

    {result?.output_path && showFinish && <div style={{marginTop:12,gridColumn:"1 / -1"}}>
      <VocalRack API={API}
        sourceJobId={pitchResult?.output_path?pitchJobId:jobId}
        sourceName={pitchResult?.output_path?"pitch-polished vocal":"converted vocal"}/>
    </div>}
  </div>;
}
