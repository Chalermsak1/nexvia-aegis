"""
experiments/build_visualizer_html.py — Injects simulation telemetry into a self-contained 3D WebGL HTML visualizer.
"""

from __future__ import annotations

import json
import os


def generate_visualizer_html(
    json_path: str = "results/swarm_trajectories.json",
    html_out_path: str = "results/visualizer_swarm_3d.html",
) -> None:
    with open(json_path, mode="r", encoding="utf-8") as f:
        telemetry = json.load(f)

    telemetry_json_str = json.dumps(telemetry)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NEXVIA AEGIS — 3D MuJoCo Swarm Simulation & CBF / BRMC Visualizer</title>
  <style>
    * {{
      margin: 0;
      padding: 0;
      box-sizing: border-box;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    body {{
      background: #090d16;
      color: #f1f5f9;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      height: 100vh;
    }}
    #header {{
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 10;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}
    .badge-safe {{ background: #065f46; color: #34d399; border: 1px solid #10b981; }}
    .badge-warn {{ background: #854d0e; color: #fde047; border: 1px solid #eab308; }}
    .badge-danger {{ background: #991b1b; color: #fca5a5; border: 1px solid #ef4444; }}
    
    #canvas-container {{
      flex: 1;
      position: relative;
      width: 100%;
      height: 100%;
    }}
    #sidebar {{
      position: absolute;
      top: 16px;
      right: 16px;
      width: 320px;
      background: rgba(15, 23, 42, 0.82);
      backdrop-filter: blur(14px);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 12px;
      padding: 16px;
      z-index: 5;
      font-size: 13px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }}
    .sidebar-section {{ margin-bottom: 14px; }}
    .sidebar-title {{
      font-size: 11px;
      text-transform: uppercase;
      color: #94a3b8;
      font-weight: 700;
      letter-spacing: 0.8px;
      margin-bottom: 6px;
    }}
    .stat-row {{
      display: flex;
      justify-content: space-between;
      padding: 4px 0;
      border-bottom: 1px solid rgba(255,255,255,0.05);
    }}
    .stat-val {{ font-weight: 600; font-family: monospace; }}
    
    #controls-bar {{
      background: rgba(15, 23, 42, 0.9);
      backdrop-filter: blur(12px);
      border-top: 1px solid rgba(255, 255, 255, 0.1);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      gap: 16px;
      z-index: 10;
    }}
    .btn {{
      background: #1e293b;
      color: #f8fafc;
      border: 1px solid rgba(255, 255, 255, 0.15);
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      transition: all 0.2s;
    }}
    .btn:hover {{ background: #334155; border-color: #38bdf8; }}
    .btn-primary {{ background: #0284c7; border-color: #38bdf8; }}
    .btn-primary:hover {{ background: #0369a1; }}
    #scrubber {{
      flex: 1;
      accent-color: #0284c7;
      cursor: pointer;
    }}
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>

  <div id="header">
    <div style="display: flex; align-items: center; gap: 12px;">
      <h2 style="font-size: 16px; font-weight: 700; letter-spacing: -0.3px;">NEXVIA AEGIS — 3D Swarm Interactive Physics Visualizer</h2>
      <span class="badge badge-safe" id="status-badge">CBF ACTIVE · BRMC QUARANTINE READY</span>
    </div>
    <div style="font-size: 13px; color: #94a3b8;">
      MuJoCo Continuous 3D Rigid Body · High-Order CBF · Ornstein-Uhlenbeck Wind
    </div>
  </div>

  <div id="canvas-container">
    <div id="sidebar">
      <div class="sidebar-section">
        <div class="sidebar-title">Simulation State</div>
        <div class="stat-row"><span>Time:</span><span class="stat-val" id="stat-time">0.00 s</span></div>
        <div class="stat-row"><span>Step:</span><span class="stat-val" id="stat-step">0 / 250</span></div>
        <div class="stat-row"><span>Wind Vector:</span><span class="stat-val" id="stat-wind">[0, 0, 0]</span></div>
        <div class="stat-row"><span>Min Obstacle Clearance:</span><span class="stat-val" id="stat-obs-dist">--</span></div>
        <div class="stat-row"><span>Min Inter-Agent Clearance:</span><span class="stat-val" id="stat-inter-dist">--</span></div>
      </div>

      <div class="sidebar-section">
        <div class="sidebar-title">Consensus & Invariants</div>
        <div class="stat-row"><span>Consensus Position:</span><span class="stat-val" id="stat-pos">--</span></div>
        <div class="stat-row"><span>Target Distance Error:</span><span class="stat-val" id="stat-error">--</span></div>
        <div class="stat-row"><span>Ville Threshold (1/α):</span><span class="stat-val">20.00</span></div>
        <div class="stat-row"><span>Quarantined Agents:</span><span class="stat-val" id="stat-quarantined" style="color:#ef4444;">None</span></div>
      </div>

      <div class="sidebar-section">
        <div class="sidebar-title">Agent Test Martingale Wealth (M_t)</div>
        <div id="wealth-bars"></div>
      </div>
    </div>
  </div>

  <div id="controls-bar">
    <button class="btn btn-primary" id="play-btn">Play</button>
    <button class="btn" id="prev-btn">◀ Step</button>
    <button class="btn" id="next-btn">Step ▶</button>
    <button class="btn" id="reset-btn">Reset</button>
    <input type="range" id="scrubber" min="0" max="249" value="0">
    <span style="font-family: monospace; font-size: 12px; min-width: 65px;" id="frame-counter">0 / 250</span>
    <select class="btn" id="speed-select" style="padding: 5px 8px;">
      <option value="0.5">0.5x Speed</option>
      <option value="1" selected>1.0x Speed</option>
      <option value="2">2.0x Speed</option>
      <option value="4">4.0x Speed</option>
    </select>
  </div>

  <script id="telemetryData" type="application/json">
{telemetry_json_str}
  </script>

  <script>
    const data = JSON.parse(document.getElementById('telemetryData').textContent);
    const meta = data.metadata;
    const frames = data.frames;
    const totalFrames = frames.length;

    let currentFrameIdx = 0;
    let isPlaying = false;
    let playSpeed = 1.0;
    let lastAnimTime = 0;

    // Three.js Setup
    const container = document.getElementById('canvas-container');
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x090d16);
    scene.fog = new THREE.FogExp2(0x090d16, 0.05);

    const camera = new THREE.PerspectiveCamera(50, container.clientWidth / container.clientHeight, 0.1, 100);
    camera.position.set(0, -5.5, 4.5);
    camera.up.set(0, 0, 1); // Z is UP

    const renderer = new THREE.WebGLRenderer({{ antialias: true }});
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    container.appendChild(renderer.domElement);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.target.set(0.5, 0.5, 0.5);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
    dirLight.position.set(5, -5, 8);
    dirLight.castShadow = true;
    scene.add(dirLight);

    // Floor Grid
    const grid = new THREE.GridHelper(7, 14, 0x0284c7, 0x1e293b);
    grid.rotation.x = Math.PI / 2;
    scene.add(grid);

    // Target Marker
    const targetGeom = new THREE.SphereGeometry(meta.target_arrival_radius, 24, 24);
    const targetMat = new THREE.MeshStandardMaterial({{ color: 0x22c55e, transparent: true, opacity: 0.45, wireframe: true }});
    const targetMesh = new THREE.Mesh(targetGeom, targetMat);
    targetMesh.position.set(meta.target_pos[0], meta.target_pos[1], meta.target_pos[2]);
    scene.add(targetMesh);

    // Obstacles
    const obsMeshes = [];
    meta.obstacles.forEach(obs => {{
      const geom = new THREE.SphereGeometry(obs.radius, 24, 24);
      const mat = new THREE.MeshStandardMaterial({{ color: 0xef4444, roughness: 0.4, transparent: true, opacity: 0.75 }});
      const mesh = new THREE.Mesh(geom, mat);
      mesh.position.set(obs.center[0], obs.center[1], obs.center[2]);
      scene.add(mesh);
      obsMeshes.push(mesh);

      // Wireframe safety perimeter
      const wireGeom = new THREE.SphereGeometry(obs.radius + meta.robot_radius + 0.12, 16, 16);
      const wireMat = new THREE.MeshBasicMaterial({{ color: 0xf87171, wireframe: true, transparent: true, opacity: 0.25 }});
      const wireMesh = new THREE.Mesh(wireGeom, wireMat);
      wireMesh.position.set(obs.center[0], obs.center[1], obs.center[2]);
      scene.add(wireMesh);
    }});

    // Robots
    const robotMeshes = [];
    const trailGeoms = [];
    const trailLines = [];
    const trailPoints = [];

    for (let i = 0; i < meta.num_robots; i++) {{
      const geom = new THREE.SphereGeometry(meta.robot_radius, 24, 24);
      const isByz = i === 4;
      const mat = new THREE.MeshStandardMaterial({{
        color: isByz ? 0xf59e0b : 0x0284c7,
        roughness: 0.3,
        metalness: 0.5,
      }});
      const mesh = new THREE.Mesh(geom, mat);
      mesh.castShadow = true;
      scene.add(mesh);
      robotMeshes.push(mesh);

      // Trails
      const pts = [];
      for (let t = 0; t < totalFrames; t++) {{
        const p = frames[t].robots[i].pos;
        pts.push(new THREE.Vector3(p[0], p[1], p[2]));
      }}
      trailPoints.push(pts);

      const tGeom = new THREE.BufferGeometry().setFromPoints([pts[0]]);
      const tMat = new THREE.LineBasicMaterial({{ color: isByz ? 0xef4444 : 0x38bdf8, transparent: true, opacity: 0.55 }});
      const line = new THREE.Line(tGeom, tMat);
      scene.add(line);
      trailLines.push(line);
    }}

    // Update Frame Display
    function applyFrame(idx) {{
      const f = frames[idx];
      document.getElementById('stat-time').textContent = f.time.toFixed(2) + ' s';
      document.getElementById('stat-step').textContent = `${{f.step}} / ${{totalFrames}}`;
      document.getElementById('stat-wind').textContent = `[${{f.wind.map(w => w.toFixed(2)).join(', ')}}]`;
      document.getElementById('stat-obs-dist').textContent = f.min_obs_distance.toFixed(3) + ' m';
      document.getElementById('stat-inter-dist').textContent = f.min_inter_distance.toFixed(3) + ' m';
      document.getElementById('stat-pos').textContent = `[${{f.consensus_pos.map(c => c.toFixed(2)).join(', ')}}]`;
      document.getElementById('stat-error').textContent = f.consensus_error.toFixed(3) + ' m';
      document.getElementById('scrubber').value = idx;
      document.getElementById('frame-counter').textContent = `${{idx}} / ${{totalFrames}}`;

      const qText = f.quarantined_agents.length > 0 ? `Robot(s) [${{f.quarantined_agents.join(', ')}}]` : 'None';
      document.getElementById('stat-quarantined').textContent = qText;

      const badge = document.getElementById('status-badge');
      if (f.quarantined_agents.length > 0) {{
        badge.className = 'badge badge-danger';
        badge.textContent = `BYZANTINE QUARANTINED (Agent ${{f.quarantined_agents.join(', ')}})`;
      }} else {{
        badge.className = 'badge badge-safe';
        badge.textContent = 'NOMINAL SWARM TRACKING · CBF INVARIANCE PRESERVED';
      }}

      // Update Robot positions & materials
      for (let i = 0; i < meta.num_robots; i++) {{
        const rData = f.robots[i];
        const rMesh = robotMeshes[i];
        rMesh.position.set(rData.pos[0], rData.pos[1], rData.pos[2]);

        if (rData.is_quarantined) {{
          rMesh.material.color.setHex(0xdc2626); // Crimson red
        }} else if (rData.is_byzantine) {{
          rMesh.material.color.setHex(0xf59e0b); // Amber
        }} else {{
          rMesh.material.color.setHex(0x0284c7); // Cyan Blue
        }}

        // Update trail
        const subPts = trailPoints[i].slice(0, idx + 1);
        trailLines[i].geometry.dispose();
        trailLines[i].geometry = new THREE.BufferGeometry().setFromPoints(subPts);
      }}

      // Render Wealth Bars in Sidebar
      const wContainer = document.getElementById('wealth-bars');
      wContainer.innerHTML = '';
      for (let i = 0; i < meta.num_robots; i++) {{
        const w = f.robots[i].wealth;
        const isQ = f.robots[i].is_quarantined;
        const pct = Math.min(100, (w / 25.0) * 100);
        const col = isQ ? '#ef4444' : (f.robots[i].is_byzantine ? '#f59e0b' : '#38bdf8');
        wContainer.innerHTML += `
          <div style="margin-bottom: 6px;">
            <div style="display: flex; justify-content: space-between; font-size: 11px;">
              <span>Robot ${{i}} ${{f.robots[i].is_byzantine ? '(Byzantine)' : ''}}</span>
              <span style="font-family: monospace; color: ${{col}};">M_t = ${{w.toFixed(2)}}</span>
            </div>
            <div style="height: 6px; background: #1e293b; border-radius: 3px; overflow: hidden; margin-top: 2px;">
              <div style="height: 100%; width: ${{pct}}%; background: ${{col}};"></div>
            </div>
          </div>
        `;
      }}
    }}

    // UI Event Handlers
    const playBtn = document.getElementById('play-btn');
    playBtn.addEventListener('click', () => {{
      isPlaying = !isPlaying;
      playBtn.textContent = isPlaying ? 'Pause' : 'Play';
    }});

    document.getElementById('prev-btn').addEventListener('click', () => {{
      isPlaying = false;
      playBtn.textContent = 'Play';
      currentFrameIdx = Math.max(0, currentFrameIdx - 1);
      applyFrame(currentFrameIdx);
    }});

    document.getElementById('next-btn').addEventListener('click', () => {{
      isPlaying = false;
      playBtn.textContent = 'Play';
      currentFrameIdx = Math.min(totalFrames - 1, currentFrameIdx + 1);
      applyFrame(currentFrameIdx);
    }});

    document.getElementById('reset-btn').addEventListener('click', () => {{
      isPlaying = false;
      playBtn.textContent = 'Play';
      currentFrameIdx = 0;
      applyFrame(currentFrameIdx);
    }});

    document.getElementById('scrubber').addEventListener('input', (e) => {{
      isPlaying = false;
      playBtn.textContent = 'Play';
      currentFrameIdx = parseInt(e.target.value);
      applyFrame(currentFrameIdx);
    }});

    document.getElementById('speed-select').addEventListener('change', (e) => {{
      playSpeed = parseFloat(e.target.value);
    }});

    window.addEventListener('resize', () => {{
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    }});

    // Render Loop
    applyFrame(0);

    function animate(timestamp) {{
      requestAnimationFrame(animate);

      if (isPlaying) {{
        if (!lastAnimTime) lastAnimTime = timestamp;
        const delta = (timestamp - lastAnimTime) / 1000.0;
        const frameInterval = meta.timestep / playSpeed;

        if (delta >= frameInterval) {{
          currentFrameIdx++;
          if (currentFrameIdx >= totalFrames) {{
            currentFrameIdx = totalFrames - 1;
            isPlaying = false;
            playBtn.textContent = 'Play';
          }}
          applyFrame(currentFrameIdx);
          lastAnimTime = timestamp;
        }}
      }} else {{
        lastAnimTime = timestamp;
      }}

      controls.update();
      renderer.render(scene, camera);
    }}

    requestAnimationFrame(animate);
  </script>
</body>
</html>
"""

    os.makedirs(os.path.dirname(html_out_path), exist_ok=True)
    with open(html_out_path, mode="w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[Generated Visualizer HTML]: {html_out_path} ({len(html_content)} bytes)")


if __name__ == "__main__":
    generate_visualizer_html()
