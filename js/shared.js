export const STORAGE_KEY = "guideRobotStateV1";

export const CELL_TYPES = {
  FREE: 0,
  WALL: 1,
};

export function createDefaultState() {
  return {
    map: {
      imageDataUrl: null,
      imageWidth: 0,
      imageHeight: 0,
      imageLoaded: false,
      grid: [],
      cols: 50,
      rows: 50,
      threshold: 180,
      cellSizeCm: 25,
    },

    robot: {
      home: null,
      position: null,
      direction: "E",
      status: "WAITING",
    },

    user: {
      position: null,
    },

    goal: {
      position: null,
    },

    obstacles: [],

    paths: {
      toUser: [],
      toGoal: [],
    },

    request: {
      active: false,
      id: 0,
    },

    updatedAt: Date.now(),
  };
}

export function normalizeState(rawState) {
  const defaultState = createDefaultState();
  const state = rawState && typeof rawState === "object" ? rawState : {};

  return {
    ...defaultState,
    ...state,

    map: {
      ...defaultState.map,
      ...(state.map ?? {}),
    },

    robot: {
      ...defaultState.robot,
      ...(state.robot ?? {}),
    },

    user: {
      ...defaultState.user,
      ...(state.user ?? {}),
    },

    goal: {
      ...defaultState.goal,
      ...(state.goal ?? {}),
    },

    obstacles: Array.isArray(state.obstacles) ? state.obstacles : [],

    paths: {
      ...defaultState.paths,
      ...(state.paths ?? {}),
    },

    request: {
      ...defaultState.request,
      ...(state.request ?? {}),
    },
  };
}

export function loadAppState() {
  try {
    const text = localStorage.getItem(STORAGE_KEY);

    if (!text) {
      return createDefaultState();
    }

    return normalizeState(JSON.parse(text));
  } catch {
    return createDefaultState();
  }
}

export function saveAppState(state) {
  const nextState = normalizeState(state);
  nextState.updatedAt = Date.now();

  localStorage.setItem(STORAGE_KEY, JSON.stringify(nextState));
  return nextState;
}

export function resetAppState() {
  const state = createDefaultState();
  saveAppState(state);
  return state;
}

export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("ファイル読み込みに失敗しました"));

    reader.readAsDataURL(file);
  });
}

export function loadImageFromSrc(src) {
  return new Promise((resolve, reject) => {
    if (!src) {
      reject(new Error("画像データがありません"));
      return;
    }

    const image = new Image();

    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("画像の読み込みに失敗しました"));

    image.src = src;
  });
}

export function generateGridFromImage(image, cols, threshold) {
  const cellSizePx = image.width / cols;
  const rows = Math.max(1, Math.floor(image.height / cellSizePx));

  const offscreen = document.createElement("canvas");
  offscreen.width = image.width;
  offscreen.height = image.height;

  const offCtx = offscreen.getContext("2d");
  offCtx.drawImage(image, 0, 0);

  const imageData = offCtx.getImageData(0, 0, image.width, image.height);
  const grid = createEmptyGrid(cols, rows);

  for (let gy = 0; gy < rows; gy++) {
    for (let gx = 0; gx < cols; gx++) {
      const startX = Math.floor(gx * cellSizePx);
      const startY = Math.floor(gy * cellSizePx);
      const endX = Math.min(image.width, Math.floor((gx + 1) * cellSizePx));
      const endY = Math.min(image.height, Math.floor((gy + 1) * cellSizePx));

      let darkCount = 0;
      let totalCount = 0;

      for (let y = startY; y < endY; y++) {
        for (let x = startX; x < endX; x++) {
          const index = (y * image.width + x) * 4;
          const r = imageData.data[index];
          const g = imageData.data[index + 1];
          const b = imageData.data[index + 2];

          const brightness = (r + g + b) / 3;

          if (brightness < threshold) {
            darkCount++;
          }

          totalCount++;
        }
      }

      const darkRatio = totalCount > 0 ? darkCount / totalCount : 0;
      grid[gy][gx] = darkRatio >= 0.3 ? CELL_TYPES.WALL : CELL_TYPES.FREE;
    }
  }

  return { rows, grid };
}

export function createEmptyGrid(cols, rows) {
  return Array.from({ length: rows }, () => {
    return Array.from({ length: cols }, () => CELL_TYPES.FREE);
  });
}

export function getMapLayout(canvas, image) {
  if (!image) {
    return {
      scale: 1,
      ox: 0,
      oy: 0,
      drawW: canvas.width,
      drawH: canvas.height,
    };
  }

  const scale = Math.min(
    canvas.width / image.width,
    canvas.height / image.height
  );

  const drawW = image.width * scale;
  const drawH = image.height * scale;

  const ox = (canvas.width - drawW) / 2;
  const oy = (canvas.height - drawH) / 2;

  return { scale, ox, oy, drawW, drawH };
}

export function getCellFromMouseEvent(canvas, event, image, state) {
  if (!image) {
    return null;
  }

  const rect = canvas.getBoundingClientRect();

  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;

  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;

  const canvasX = x * scaleX;
  const canvasY = y * scaleY;

  const layout = getMapLayout(canvas, image);

  const imageX = (canvasX - layout.ox) / layout.scale;
  const imageY = (canvasY - layout.oy) / layout.scale;

  if (
    imageX < 0 ||
    imageY < 0 ||
    imageX >= image.width ||
    imageY >= image.height
  ) {
    return null;
  }

  const cellSizePx = image.width / state.map.cols;

  const gx = Math.floor(imageX / cellSizePx);
  const gy = Math.floor(imageY / cellSizePx);

  if (
    gx < 0 ||
    gy < 0 ||
    gx >= state.map.cols ||
    gy >= state.map.rows
  ) {
    return null;
  }

  return { x: gx, y: gy };
}

export function isSameCell(a, b) {
  return Boolean(a && b && a.x === b.x && a.y === b.y);
}

export function isWallCell(state, cell) {
  if (!state.map.grid.length) return false;
  return state.map.grid[cell.y]?.[cell.x] === CELL_TYPES.WALL;
}

export function isObstacleCell(state, cell) {
  return state.obstacles.some((obstacle) => {
    return isSameCell(obstacle, cell);
  });
}

export function isBlockedCell(state, cell) {
  if (
    cell.x < 0 ||
    cell.y < 0 ||
    cell.x >= state.map.cols ||
    cell.y >= state.map.rows
  ) {
    return true;
  }

  if (isWallCell(state, cell)) {
    return true;
  }

  if (isObstacleCell(state, cell)) {
    return true;
  }

  return false;
}

export function cellKey(cell) {
  return `${cell.x},${cell.y}`;
}

export function findPathBfs(state, start, goal) {
  if (!start || !goal) {
    return [];
  }

  const queue = [];
  const visited = new Set();
  const parent = new Map();

  const startKey = cellKey(start);
  const goalKey = cellKey(goal);

  queue.push(start);
  visited.add(startKey);

  const directions = [
    { x: 0, y: -1 },
    { x: 1, y: 0 },
    { x: 0, y: 1 },
    { x: -1, y: 0 },
  ];

  while (queue.length > 0) {
    const current = queue.shift();
    const currentKey = cellKey(current);

    if (currentKey === goalKey) {
      return reconstructPath(parent, start, goal);
    }

    for (const direction of directions) {
      const next = {
        x: current.x + direction.x,
        y: current.y + direction.y,
      };

      const nextKey = cellKey(next);

      if (visited.has(nextKey)) continue;
      if (isBlockedCell(state, next)) continue;

      visited.add(nextKey);
      parent.set(nextKey, current);
      queue.push(next);
    }
  }

  return [];
}

export function reconstructPath(parent, start, goal) {
  const path = [];
  let current = { ...goal };

  while (!isSameCell(current, start)) {
    path.push(current);

    const previous = parent.get(cellKey(current));

    if (!previous) {
      return [];
    }

    current = previous;
  }

  path.push(start);
  path.reverse();

  return path;
}

export function clearPaths(state) {
  state.paths.toUser = [];
  state.paths.toGoal = [];
}

export function canCalculateGuidePaths(state) {
  return Boolean(
    state.robot.home &&
    state.user.position &&
    state.goal.position
  );
}

export function calculateGuidePaths(state) {
  clearPaths(state);

  if (!canCalculateGuidePaths(state)) {
    state.robot.status = "WAITING";
    return false;
  }

  const pathToUser = findPathBfs(state, state.robot.home, state.user.position);

  if (pathToUser.length === 0) {
    state.robot.status = "ERROR";
    return false;
  }

  const pathToGoal = findPathBfs(state, state.user.position, state.goal.position);

  if (pathToGoal.length === 0) {
    state.paths.toUser = pathToUser;
    state.robot.status = "ERROR";
    return false;
  }

  state.paths.toUser = pathToUser;
  state.paths.toGoal = pathToGoal;
  state.robot.status = "ROUTE_READY";

  return true;
}

export function drawScene({
  canvas,
  ctx,
  state,
  image,
  showPaths = true,
  showHome = true,
  showRobot = true,
  showUser = true,
  showGoal = true,
  showObstacles = true,
}) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = "#10141d";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  if (!image) {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = "#222222";
    ctx.font = "18px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("親機でマップ画像を読み込んでください", canvas.width / 2, canvas.height / 2);
    return;
  }

  const layout = getMapLayout(canvas, image);

  ctx.drawImage(
    image,
    layout.ox,
    layout.oy,
    layout.drawW,
    layout.drawH
  );

  if (showPaths) {
    drawPath(canvas, ctx, state, image, state.paths.toUser, "rgba(0, 174, 255, 0.65)");
    drawPath(canvas, ctx, state, image, state.paths.toGoal, "rgba(255, 214, 102, 0.75)");
  }

  drawGridLines(canvas, ctx, state, image);

  if (showObstacles) {
    for (const obstacle of state.obstacles) {
      drawCell(canvas, ctx, state, image, obstacle, "rgba(155, 89, 182, 0.9)", "障");
    }
  }

  if (showHome && state.robot.home) {
    drawCell(
      canvas,
      ctx,
      state,
      image,
      state.robot.home,
      "rgba(52, 152, 219, 0.95)",
      directionSymbol(state.robot.direction)
    );
  }

  if (
    showRobot &&
    state.robot.position &&
    !isSameCell(state.robot.position, state.robot.home)
  ) {
    drawCell(
      canvas,
      ctx,
      state,
      image,
      state.robot.position,
      "rgba(243, 156, 18, 0.95)",
      "R"
    );
  }

  if (showUser && state.user.position) {
    drawCell(canvas, ctx, state, image, state.user.position, "rgba(231, 76, 60, 0.95)", "人");
  }

  if (showGoal && state.goal.position) {
    drawCell(canvas, ctx, state, image, state.goal.position, "rgba(46, 204, 113, 0.95)", "G");
  }
}

function drawPath(canvas, ctx, state, image, path, color) {
  if (!path || path.length === 0) return;

  const layout = getMapLayout(canvas, image);
  const cellSizePx = image.width / state.map.cols;

  ctx.save();
  ctx.translate(layout.ox, layout.oy);
  ctx.scale(layout.scale, layout.scale);

  ctx.fillStyle = color;

  for (const cell of path) {
    ctx.fillRect(
      cell.x * cellSizePx,
      cell.y * cellSizePx,
      cellSizePx,
      cellSizePx
    );
  }

  ctx.restore();
}

function drawGridLines(canvas, ctx, state, image) {
  const layout = getMapLayout(canvas, image);
  const cellSizePx = image.width / state.map.cols;

  ctx.save();
  ctx.translate(layout.ox, layout.oy);
  ctx.scale(layout.scale, layout.scale);

  ctx.strokeStyle = "rgb(0, 0, 0)";
  ctx.lineWidth = 0.45;

  for (let y = 0; y <= state.map.rows; y++) {
    ctx.beginPath();
    ctx.moveTo(0, y * cellSizePx);
    ctx.lineTo(state.map.cols * cellSizePx, y * cellSizePx);
    ctx.stroke();
  }

  for (let x = 0; x <= state.map.cols; x++) {
    ctx.beginPath();
    ctx.moveTo(x * cellSizePx, 0);
    ctx.lineTo(x * cellSizePx, state.map.rows * cellSizePx);
    ctx.stroke();
  }

  ctx.restore();
}

export function drawCell(canvas, ctx, state, image, cell, color, label) {
  const layout = getMapLayout(canvas, image);
  const cellSizePx = image.width / state.map.cols;

  const px = layout.ox + cell.x * cellSizePx * layout.scale;
  const py = layout.oy + cell.y * cellSizePx * layout.scale;
  const size = cellSizePx * layout.scale;

  ctx.save();

  ctx.fillStyle = color;
  ctx.fillRect(px, py, size, size);

  ctx.fillStyle = "#ffffff";
  ctx.font = `${Math.max(10, Math.floor(size * 0.5))}px sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, px + size / 2, py + size / 2);

  ctx.restore();
}

export function directionSymbol(direction) {
  const symbols = {
    N: "↑",
    E: "→",
    S: "↓",
    W: "←",
  };

  return symbols[direction] ?? "R";
}

export function cellToLabel(cell) {
  return cell ? `(${cell.x}, ${cell.y})` : "未設定";
}