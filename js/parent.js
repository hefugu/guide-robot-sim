import {
  calculateGuidePaths,
  canCalculateGuidePaths,
  clearPaths,
  drawScene,
  fileToDataUrl,
  findPathBfs,
  generateGridFromImage,
  getCellFromMouseEvent,
  isObstacleCell,
  isSameCell,
  isWallCell,
  loadAppState,
  loadImageFromSrc,
  resetAppState,
  saveAppState,
} from "./shared.js";

import {
  commandsToJson,
  commandsToText,
  mergeGuidePath,
  pathToCommands,
} from "./commands.js";

const canvas = document.getElementById("mapCanvas");
const ctx = canvas.getContext("2d");

const elements = {
  mapFile: document.getElementById("mapFile"),
  thresholdInput: document.getElementById("thresholdInput"),
  thresholdValue: document.getElementById("thresholdValue"),
  gridColsInput: document.getElementById("gridColsInput"),
  gridRowsInput: document.getElementById("gridRowsInput"),
  cellSizeInput: document.getElementById("cellSizeInput"),
  btnGenerateGrid: document.getElementById("btnGenerateGrid"),

  toolHome: document.getElementById("toolHome"),
  toolObstacle: document.getElementById("toolObstacle"),
  toolErase: document.getElementById("toolErase"),
  directionSelect: document.getElementById("directionSelect"),

  btnResetAll: document.getElementById("btnResetAll"),
  btnClearLog: document.getElementById("btnClearLog"),
  robotEndpointInput: document.getElementById("robotEndpointInput"),

  statusLabel: document.getElementById("statusLabel"),
  toolLabel: document.getElementById("toolLabel"),
  logOutput: document.getElementById("logOutput"),
  commandOutput: document.getElementById("commandOutput"),
  btnCopyCommandJson: document.getElementById("btnCopyCommandJson"),
  btnDownloadCommandJson: document.getElementById("btnDownloadCommandJson"),
  stateOutput: document.getElementById("stateOutput"),
};

let appState = loadAppState();
let mapImage = null;
let currentImageDataUrl = null;
let currentTool = "home";

let simulationTimer = null;
let obstaclePauseTimer = null;
let runningRequestId = null;
let currentTargetMode = "IDLE";
let sendingRequestId = null;

const ROBOT_ENDPOINT_KEY = "guideRobotEndpointV1";
const ROBOT_ENDPOINT = "http://192.168.11.48:8000";
const OLD_DEFAULT_ENDPOINT = "http://raspberrypi.local:8765/commands";

function log(message) {
  const time = new Date().toLocaleTimeString();
  elements.logOutput.value += `[${time}] ${message}\n`;
  elements.logOutput.scrollTop = elements.logOutput.scrollHeight;
}

function saveAndRender() {
  appState = saveAppState(appState);
  render();
}

async function ensureMapImage() {
  const imageDataUrl = appState.map.imageDataUrl;

  if (!imageDataUrl) {
    mapImage = null;
    currentImageDataUrl = null;
    return;
  }

  if (currentImageDataUrl === imageDataUrl && mapImage) {
    return;
  }

  mapImage = await loadImageFromSrc(imageDataUrl);
  currentImageDataUrl = imageDataUrl;
}

function updateStateOutput() {
  const view = {
    map: {
      cols: appState.map.cols,
      rows: appState.map.rows,
      threshold: appState.map.threshold,
      cellSizeCm: appState.map.cellSizeCm,
      imageLoaded: appState.map.imageLoaded,
    },
    robot: appState.robot,
    user: appState.user,
    goal: appState.goal,
    obstacles: appState.obstacles,
    paths: {
      toUserLength: appState.paths.toUser.length,
      toGoalLength: appState.paths.toGoal.length,
    },
    commands: {
      count: appState.commands.list.length,
    },
    request: appState.request,
    simulation: {
      runningRequestId,
      currentTargetMode,
      timerRunning: Boolean(simulationTimer),
      obstaclePauseRunning: Boolean(obstaclePauseTimer),
    },
  };

  elements.statusLabel.textContent = appState.robot.status;
  elements.toolLabel.textContent = getToolLabel(currentTool);
  elements.commandOutput.value = appState.commands.text || "";
  elements.stateOutput.textContent = JSON.stringify(view, null, 2);
}

function getToolLabel(tool) {
  const labels = {
    home: "待機位置",
    obstacle: "障害物",
    erase: "消去",
  };

  return labels[tool] ?? tool;
}

function setTool(tool) {
  currentTool = tool;

  elements.toolHome.classList.toggle("active", tool === "home");
  elements.toolObstacle.classList.toggle("active", tool === "obstacle");
  elements.toolErase.classList.toggle("active", tool === "erase");

  log(`ツール変更: ${getToolLabel(tool)}`);
  updateStateOutput();
}

function removeObstacleAt(cell) {
  appState.obstacles = appState.obstacles.filter((obstacle) => {
    return !isSameCell(obstacle, cell);
  });
}

function eraseAt(cell) {
  if (isSameCell(appState.robot.home, cell)) {
    appState.robot.home = null;
    appState.robot.position = null;
    log(`待機位置を削除: (${cell.x}, ${cell.y})`);
  }

  if (isSameCell(appState.user.position, cell)) {
    appState.user.position = null;
    log(`利用者位置を削除: (${cell.x}, ${cell.y})`);
  }

  if (isSameCell(appState.goal.position, cell)) {
    appState.goal.position = null;
    log(`目的地を削除: (${cell.x}, ${cell.y})`);
  }

  const beforeCount = appState.obstacles.length;
  removeObstacleAt(cell);

  if (appState.obstacles.length !== beforeCount) {
    log(`障害物を削除: (${cell.x}, ${cell.y})`);
  }
}

function updateCommandsFromPaths() {
  const mergedPath = mergeGuidePath(
    appState.paths.toUser,
    appState.paths.toGoal
  );

  const commands = pathToCommands(
    mergedPath,
    appState.robot.direction
  );

  appState.commands.list = commands;
  appState.commands.text = commandsToText(commands);
  appState.commands.json = commandsToJson(commands);
}

function getCommandJsonForExport() {
  const json = appState.commands.json;

  if (json && json.trim().length > 0) {
    return json;
  }

  return JSON.stringify(appState.commands.list ?? [], null, 2);
}

async function sendCommandsToRobot() {
  const endpoint = elements.robotEndpointInput.value.trim();
  if (!endpoint) throw new Error("ロボット送信先が設定されていません");

  localStorage.setItem(ROBOT_ENDPOINT_KEY, endpoint);
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: getCommandJsonForExport(),
  });

  let result = null;
  try { result = await response.json(); } catch { /* HTTP statusで報告 */ }
  if (!response.ok) {
    throw new Error(result?.error || `ロボット送信失敗 (HTTP ${response.status})`);
  }
  log(`ロボットへJSONを送信しました (${result?.commandCount ?? appState.commands.list.length}命令)`);
}

async function copyCommandJson() {
  const json = getCommandJsonForExport();

  if (!json || json === "[]") {
    log("JSONコピー不可: 命令列がありません");
    return;
  }

  try {
    await navigator.clipboard.writeText(json);
    log("命令列JSONをクリップボードにコピーしました");
  } catch {
    const temp = document.createElement("textarea");
    temp.value = json;
    document.body.appendChild(temp);
    temp.select();
    document.execCommand("copy");
    document.body.removeChild(temp);

    log("命令列JSONをクリップボードにコピーしました");
  }
}

function downloadCommandJson() {
  const json = getCommandJsonForExport();

  if (!json || json === "[]") {
    log("JSON保存不可: 命令列がありません");
    return;
  }

  const blob = new Blob([json], {
    type: "application/json",
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  const timestamp = new Date()
    .toISOString()
    .replaceAll(":", "-")
    .replaceAll(".", "-");

  link.href = url;
  link.download = `test_commands_${timestamp}.json`;

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(url);

  log("命令列JSONを保存しました");
}

function refreshRoutesAfterEdit(reason) {
  clearPaths(appState);

  if (canCalculateGuidePaths(appState)) {
    const ok = calculateGuidePaths(appState);

    if (ok) {
      updateCommandsFromPaths();
      log(`${reason}: 経路と命令列を再計算しました`);
    } else {
      log(`${reason}: 経路探索に失敗しました`);
    }
  } else {
    if (!appState.request.active) {
      appState.robot.status = "WAITING";
    }
  }
}

async function render() {
  await ensureMapImage();

  drawScene({
    canvas,
    ctx,
    state: appState,
    image: mapImage,
    showPaths: true,
    showHome: true,
    showRobot: true,
    showUser: true,
    showGoal: true,
    showObstacles: true,
  });

  updateStateOutput();
}

function handleCanvasClick(event) {
  if (!mapImage) {
    log("マップ画像が未読み込みです");
    return;
  }

  const cell = getCellFromMouseEvent(canvas, event, mapImage, appState);

  if (!cell) {
    return;
  }

  log(`クリック座標: (${cell.x}, ${cell.y})`);

  if (currentTool !== "erase" && isWallCell(appState, cell)) {
    log(`壁マスには配置できません: (${cell.x}, ${cell.y})`);
    return;
  }

  if (currentTool === "home") {
    stopSimulation();

    appState.robot.home = { ...cell };
    appState.robot.position = { ...cell };
    appState.robot.direction = elements.directionSelect.value;
    appState.robot.status = "WAITING";
    appState.request.active = false;

    log(`待機位置を設定: (${cell.x}, ${cell.y}), 向き=${appState.robot.direction}`);
  }

  if (currentTool === "obstacle") {
    removeObstacleAt(cell);
    appState.obstacles.push({ ...cell });
    log(`障害物を設定: (${cell.x}, ${cell.y})`);

    if (simulationTimer && appState.robot.position) {
      appState.robot.status = "REPLANNING";
    }
  }

  if (currentTool === "erase") {
    eraseAt(cell);
  }

  refreshRoutesAfterEdit("親機側の配置変更");
  saveAndRender();
}

async function handleMapFileChange(event) {
  const file = event.target.files?.[0];

  if (!file) return;

  try {
    stopSimulation();

    const dataUrl = await fileToDataUrl(file);
    const image = await loadImageFromSrc(dataUrl);

    const cols = Number(elements.gridColsInput.value);
    const threshold = Number(elements.thresholdInput.value);
    const cellSizeCm = Number(elements.cellSizeInput.value);

    const generated = generateGridFromImage(image, cols, threshold);

    appState.map.imageDataUrl = dataUrl;
    appState.map.imageWidth = image.width;
    appState.map.imageHeight = image.height;
    appState.map.imageLoaded = true;
    appState.map.cols = cols;
    appState.map.rows = generated.rows;
    appState.map.threshold = threshold;
    appState.map.cellSizeCm = cellSizeCm;
    appState.map.grid = generated.grid;

    elements.gridRowsInput.value = String(generated.rows);

    clearPaths(appState);
    appState.request.active = false;
    appState.robot.status = "WAITING";

    log(`画像読み込み成功: ${file.name} (${image.width} x ${image.height})`);
    log(`マップ生成完了: ${cols} x ${generated.rows}, 1マス=${cellSizeCm}cm`);

    appState = saveAppState(appState);
    await render();
  } catch (error) {
    log(error.message);
  }
}

async function regenerateGrid() {
  if (!mapImage) {
    log("マップ画像が未読み込みです");
    return;
  }

  stopSimulation();

  const cols = Number(elements.gridColsInput.value);
  const threshold = Number(elements.thresholdInput.value);
  const cellSizeCm = Number(elements.cellSizeInput.value);

  const generated = generateGridFromImage(mapImage, cols, threshold);

  appState.map.cols = cols;
  appState.map.rows = generated.rows;
  appState.map.threshold = threshold;
  appState.map.cellSizeCm = cellSizeCm;
  appState.map.grid = generated.grid;

  elements.gridRowsInput.value = String(generated.rows);

  refreshRoutesAfterEdit("マップ再生成");

  log(`マップ生成完了: ${cols} x ${generated.rows}, 1マス=${cellSizeCm}cm`);
  saveAndRender();
}

function stopSimulation() {
  if (simulationTimer) {
    clearInterval(simulationTimer);
    simulationTimer = null;
  }

  if (obstaclePauseTimer) {
    clearTimeout(obstaclePauseTimer);
    obstaclePauseTimer = null;
  }

  runningRequestId = null;
  currentTargetMode = "IDLE";
}

function getCurrentTarget() {
  if (currentTargetMode === "TO_USER") {
    return appState.user.position;
  }

  if (currentTargetMode === "TO_GOAL") {
    return appState.goal.position;
  }

  return null;
}

function getCurrentPathFromRobot() {
  const currentPosition = appState.robot.position;
  const target = getCurrentTarget();

  if (!currentPosition || !target) {
    return [];
  }

  return findPathBfs(appState, currentPosition, target);
}

function setError(message) {
  stopSimulation();

  appState.robot.status = "ERROR";
  appState.request.active = false;
  clearPaths(appState);

  appState = saveAppState(appState);
  render();

  log(message);
}

function finishArrived() {
  stopSimulation();

  appState.robot.status = "ARRIVED";
  appState.request.active = false;

  appState = saveAppState(appState);
  render();

  log("目的地に到着しました");
}

function pauseForObstacleAndReplan(blockedCell) {
  if (simulationTimer) {
    clearInterval(simulationTimer);
    simulationTimer = null;
  }

  appState.robot.status = "STOPPED_BY_OBSTACLE";
  appState = saveAppState(appState);
  render();

  log(`障害物検知: 次マス (${blockedCell.x}, ${blockedCell.y}) が通行不可。停止します`);

  obstaclePauseTimer = setTimeout(() => {
    obstaclePauseTimer = null;

    if (!appState.request.active) {
      return;
    }

    const retryPath = getCurrentPathFromRobot();

    if (retryPath.length <= 1) {
      setError("再探索失敗: 迂回ルートがありません");
      return;
    }

    appState.robot.status = currentTargetMode === "TO_USER"
      ? "GO_TO_USER"
      : "GUIDING_TO_GOAL";

    calculateGuidePaths(appState);
    updateCommandsFromPaths();

    appState = saveAppState(appState);
    render();

    log("再探索成功: 案内を再開します");

    startSimulationLoop();
  }, 700);
}

function startSimulationLoop() {
  if (simulationTimer) {
    return;
  }

  simulationTimer = setInterval(() => {
    const currentPosition = appState.robot.position;

    if (!currentPosition) {
      setError("ERROR: ロボット現在位置がありません");
      return;
    }

    if (
      currentTargetMode === "TO_USER" &&
      isSameCell(currentPosition, appState.user.position)
    ) {
      currentTargetMode = "TO_GOAL";
      appState.robot.status = "GUIDING_TO_GOAL";
      log("利用者位置に到着。目的地への案内を開始します");
    }

    if (
      currentTargetMode === "TO_GOAL" &&
      isSameCell(currentPosition, appState.goal.position)
    ) {
      finishArrived();
      return;
    }

    const path = getCurrentPathFromRobot();

    if (path.length <= 1) {
      setError("ERROR: 現在位置から目標までの経路がありません");
      return;
    }

    const nextCell = path[1];

    if (isWallCell(appState, nextCell) || isObstacleCell(appState, nextCell)) {
      pauseForObstacleAndReplan(nextCell);
      return;
    }

    appState.robot.position = { ...nextCell };

    if (currentTargetMode === "TO_USER") {
      appState.robot.status = "GO_TO_USER";
    }

    if (currentTargetMode === "TO_GOAL") {
      appState.robot.status = "GUIDING_TO_GOAL";
    }

    calculateGuidePaths(appState);
    updateCommandsFromPaths();

    appState = saveAppState(appState);
    render();
  }, 260);
}

async function startSimulationIfNeeded() {
  if (!appState.request.active) {
    return;
  }

  if (simulationTimer || obstaclePauseTimer) {
    return;
  }

  if (runningRequestId === appState.request.id) {
    return;
  }

  if (sendingRequestId === appState.request.id) return;

  const ok = calculateGuidePaths(appState);

  if (!ok) {
    setError("案内開始失敗: 経路が見つかりません");
    return;
  }

  updateCommandsFromPaths();

  const requestId = appState.request.id;
  sendingRequestId = requestId;
  try {
    await sendCommandsToRobot();
  } catch (error) {
    sendingRequestId = null;
    setError(`案内開始失敗: ${error.message}`);
    return;
  }
  sendingRequestId = null;
  if (!appState.request.active || appState.request.id !== requestId) return;

  runningRequestId = requestId;
  currentTargetMode = "TO_USER";

  appState.robot.position = appState.robot.home
    ? { ...appState.robot.home }
    : null;

  if (!appState.robot.position) {
    setError("案内開始失敗: ロボット待機位置がありません");
    return;
  }

  appState.robot.status = "GO_TO_USER";

  appState = saveAppState(appState);
  render();

  log("子機からの案内開始を受信しました");
  log("シミュレーションを開始します");

  startSimulationLoop();
}

async function syncFromStorage() {
  const latest = loadAppState();

  if (latest.updatedAt === appState.updatedAt) {
    return;
  }

  appState = latest;

  await ensureMapImage();

  elements.thresholdInput.value = String(appState.map.threshold);
  elements.thresholdValue.textContent = String(appState.map.threshold);
  elements.gridColsInput.value = String(appState.map.cols);
  elements.gridRowsInput.value = String(appState.map.rows);
  elements.cellSizeInput.value = String(appState.map.cellSizeCm);
  elements.directionSelect.value = appState.robot.direction;

  await startSimulationIfNeeded();
  render();
}

function resetAll() {
  stopSimulation();

  appState = resetAppState();

  mapImage = null;
  currentImageDataUrl = null;

  elements.mapFile.value = "";
  elements.thresholdInput.value = "180";
  elements.thresholdValue.textContent = "180";
  elements.gridColsInput.value = "141";
  elements.gridRowsInput.value = "50";
  elements.cellSizeInput.value = "50";
  elements.directionSelect.value = "E";
  elements.commandOutput.value = "";

  log("全リセットしました");
  render();
}

function bindEvents() {
  elements.mapFile.addEventListener("change", handleMapFileChange);
  elements.btnGenerateGrid.addEventListener("click", regenerateGrid);

  elements.thresholdInput.addEventListener("input", () => {
    elements.thresholdValue.textContent = elements.thresholdInput.value;
  });

  elements.toolHome.addEventListener("click", () => setTool("home"));
  elements.toolObstacle.addEventListener("click", () => setTool("obstacle"));
  elements.toolErase.addEventListener("click", () => setTool("erase"));

  elements.directionSelect.addEventListener("change", () => {
    stopSimulation();

    appState.robot.direction = elements.directionSelect.value;

    if (appState.robot.home) {
      appState.robot.position = { ...appState.robot.home };
    }

    appState.request.active = false;
    refreshRoutesAfterEdit("ロボット向き変更");
    saveAndRender();

    log(`ロボット向きを変更: ${appState.robot.direction}`);
  });

  elements.btnResetAll.addEventListener("click", resetAll);

  elements.btnClearLog.addEventListener("click", () => {
    elements.logOutput.value = "";
  });

  elements.btnCopyCommandJson.addEventListener("click", copyCommandJson);
  elements.btnDownloadCommandJson.addEventListener("click", downloadCommandJson);

  canvas.addEventListener("click", handleCanvasClick);

  window.addEventListener("storage", () => {
    syncFromStorage();
  });

  setInterval(syncFromStorage, 300);
}

function initCanvas() {
  canvas.width = 1000;
  canvas.height = 720;
}

async function init() {
  bindEvents();
  initCanvas();

  elements.thresholdInput.value = String(appState.map.threshold);
  elements.thresholdValue.textContent = String(appState.map.threshold);
  elements.gridColsInput.value = String(appState.map.cols || 141);
  elements.gridRowsInput.value = String(appState.map.rows || 50);
  elements.cellSizeInput.value = String(appState.map.cellSizeCm || 50);
  elements.directionSelect.value = appState.robot.direction;
  const savedRobotEndpoint = localStorage.getItem(ROBOT_ENDPOINT_KEY);
  elements.robotEndpointInput.value = !savedRobotEndpoint || savedRobotEndpoint === OLD_DEFAULT_ENDPOINT
    ? ROBOT_ENDPOINT
    : savedRobotEndpoint;

  setTool("home");

  await render();

  log("親機画面を起動しました");
}

init();
