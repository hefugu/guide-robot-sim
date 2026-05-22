const DIRECTIONS = ["N", "E", "S", "W"];

function getDirectionFromStep(from, to) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;

  if (dx === 1 && dy === 0) return "E";
  if (dx === -1 && dy === 0) return "W";
  if (dx === 0 && dy === 1) return "S";
  if (dx === 0 && dy === -1) return "N";

  return null;
}

function getTurnCommands(currentDirection, nextDirection) {
  if (currentDirection === nextDirection) {
    return [];
  }

  const currentIndex = DIRECTIONS.indexOf(currentDirection);
  const nextIndex = DIRECTIONS.indexOf(nextDirection);

  if (currentIndex === -1 || nextIndex === -1) {
    return [];
  }

  const diff = (nextIndex - currentIndex + 4) % 4;

  if (diff === 1) {
    return ["RIGHT"];
  }

  if (diff === 3) {
    return ["LEFT"];
  }

  if (diff === 2) {
    return ["RIGHT", "RIGHT"];
  }

  return [];
}

export function mergeGuidePath(pathToUser, pathToGoal) {
  const first = Array.isArray(pathToUser) ? pathToUser : [];
  const second = Array.isArray(pathToGoal) ? pathToGoal : [];

  if (first.length === 0) {
    return [];
  }

  if (second.length === 0) {
    return [...first];
  }

  return [
    ...first,
    ...second.slice(1),
  ];
}

export function pathToCommands(path, initialDirection = "E") {
  if (!Array.isArray(path) || path.length < 2) {
    return [];
  }

  const commands = [];
  let currentDirection = initialDirection;

  for (let i = 0; i < path.length - 1; i++) {
    const currentCell = path[i];
    const nextCell = path[i + 1];

    const nextDirection = getDirectionFromStep(currentCell, nextCell);

    if (!nextDirection) {
      commands.push({
        type: "ERROR",
        reason: "INVALID_STEP",
        from: currentCell,
        to: nextCell,
      });
      continue;
    }

    const turnCommands = getTurnCommands(currentDirection, nextDirection);

    for (const turnCommand of turnCommands) {
      commands.push({
        type: turnCommand,
        fromDirection: currentDirection,
        toDirection: nextDirection,
      });
    }

    commands.push({
      type: "FORWARD",
      from: currentCell,
      to: nextCell,
      direction: nextDirection,
    });

    currentDirection = nextDirection;
  }

  commands.push({
    type: "STOP",
  });

  return commands;
}

export function commandToText(command) {
  if (!command || !command.type) {
    return "UNKNOWN";
  }

  if (command.type === "FORWARD") {
    return `FORWARD  (${command.from.x},${command.from.y}) -> (${command.to.x},${command.to.y})`;
  }

  if (command.type === "LEFT") {
    return `LEFT     ${command.fromDirection} -> ${command.toDirection}`;
  }

  if (command.type === "RIGHT") {
    return `RIGHT    ${command.fromDirection} -> ${command.toDirection}`;
  }

  if (command.type === "STOP") {
    return "STOP";
  }

  if (command.type === "ERROR") {
    return `ERROR    ${command.reason}`;
  }

  return command.type;
}

export function commandsToText(commands) {
  if (!Array.isArray(commands) || commands.length === 0) {
    return "";
  }

  return commands
    .map((command, index) => {
      return `${String(index + 1).padStart(3, "0")}: ${commandToText(command)}`;
    })
    .join("\n");
}

export function commandsToJson(commands) {
  return JSON.stringify(commands, null, 2);
}