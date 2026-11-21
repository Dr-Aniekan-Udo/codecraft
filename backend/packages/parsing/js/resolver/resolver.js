'use strict';

// One request on stdin, one response on stdout. The helper only reads
// configuration and path metadata; it never imports or runs analysed code.

const fs = require('fs');
const path = require('path');
const ts = require('typescript');

const PROTOCOL_VERSION = 1;
const CONFIG_NAMES = ['tsconfig.json', 'jsconfig.json'];

class RequestError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

class ConfigError extends Error {}

function main() {
  let input = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => {
    input += chunk;
  });
  process.stdin.on('end', () => {
    let request;
    try {
      request = JSON.parse(input);
    } catch {
      refuse('invalid_request', 'request is not valid JSON', 1);
      return;
    }

    if (!request || request.protocol_version !== PROTOCOL_VERSION) {
      const version = request && request.protocol_version;
      refuse(
        'unsupported_protocol_version',
        `request protocol version ${String(version)} is not supported; this helper speaks version ${PROTOCOL_VERSION}`,
        1,
      );
      return;
    }

    try {
      const response = handle(request);
      write({ protocol_version: PROTOCOL_VERSION, ...response });
      process.exitCode = 0;
    } catch (error) {
      if (error instanceof RequestError) {
        refuse(error.code, error.message, 1);
      } else {
        refuse('resolver_error', error instanceof Error ? error.message : String(error), 2);
      }
    }
  });
}

function handle(request) {
  const root = validateRequest(request);
  const configCache = new Map();
  const configFiles = new Set();
  const workspaces = readWorkspaces(root, request.max_file_bytes);
  const results = request.references.map((reference) => {
    if (reference.kind === 'asset') {
      return {
        id: reference.id,
        ...resolveAsset(
          reference,
          root,
          request.max_file_bytes,
          configCache,
          configFiles,
          workspaces,
        ),
      };
    }
    return {
      id: reference.id,
      ...resolveModule(
        reference,
        root,
        request.max_file_bytes,
        configCache,
        configFiles,
        workspaces,
      ),
    };
  });

  return {
    typescript_version: ts.version,
    config_files: [...configFiles].sort(),
    results,
  };
}

function validateRequest(request) {
  if (!request || typeof request !== 'object') {
    throw new RequestError('invalid_request', 'request must be an object');
  }
  if (typeof request.repository_root !== 'string' || !path.isAbsolute(request.repository_root)) {
    throw new RequestError('invalid_request', 'repository_root must be an absolute path');
  }
  const root = path.resolve(request.repository_root);
  if (!isDirectory(root)) {
    throw new RequestError('invalid_request', 'repository_root must be an existing directory');
  }
  if (!Number.isInteger(request.max_file_bytes) || request.max_file_bytes <= 0) {
    throw new RequestError('invalid_request', 'max_file_bytes must be a positive integer');
  }
  if (!Array.isArray(request.references)) {
    throw new RequestError('invalid_request', 'references must be an array');
  }

  const ids = new Set();
  for (const reference of request.references) {
    if (!reference || typeof reference !== 'object') {
      throw new RequestError('invalid_request', 'each reference must be an object');
    }
    if (typeof reference.id !== 'string' || reference.id.length === 0 || ids.has(reference.id)) {
      throw new RequestError('invalid_request', 'each reference id must be a unique non-empty string');
    }
    ids.add(reference.id);
    if (typeof reference.source !== 'string' || !isRepositoryRelative(reference.source)) {
      throw new RequestError('invalid_request', 'each reference source must be a repository-relative path');
    }
    const source = path.resolve(root, ...reference.source.split('/'));
    if (!isInside(root, source) || !isFile(source)) {
      throw new RequestError('invalid_request', 'each reference source must name a file inside repository_root');
    }
    if (typeof reference.specifier !== 'string' || reference.specifier.length === 0) {
      throw new RequestError('invalid_request', 'each reference specifier must be a non-empty string');
    }
    if (reference.kind !== 'module' && reference.kind !== 'asset') {
      throw new RequestError('invalid_request', 'reference kind must be module or asset');
    }
  }
  return root;
}

function resolveModule(reference, root, maxFileBytes, configCache, configFiles, workspaces) {
  const source = path.resolve(root, ...reference.source.split('/'));
  const specifier = stripSuffix(reference.specifier);
  const configPath = nearestConfig(source, root);
  let options = {};

  if (configPath !== null) {
    configFiles.add(toRelative(root, configPath));
    const loaded = loadConfig(configPath, maxFileBytes, configCache, workspaces, root);
    if (loaded.error !== undefined) {
      return unresolved(loaded.error);
    }
    options = loaded.options;
  }

  const aliasMatched = configPath !== null && aliasMatches(specifier, options);
  const resolution = ts.resolveModuleName(
    specifier,
    source,
    options,
    resolutionHost(maxFileBytes),
  );
  if (resolution.resolvedModule !== undefined) {
    const resolved = path.normalize(resolution.resolvedModule.resolvedFileName);
    if (!isInside(root, resolved)) {
      return unresolved('resolved path is outside the repository');
    }
    // A path alias wins even when it shadows a workspace package. A workspace
    // package is only rejected when the compiler reached it through node_modules
    // without an alias, because the map must not depend on an install.
    const workspaceShadowed =
      !aliasMatched &&
      isDependencyPath(resolved) &&
      findWorkspacePackage(specifier, workspaces) !== null;
    if (!workspaceShadowed) {
      const configResolved =
        aliasMatched ||
        (!isDependencyPath(resolved) &&
          !specifier.startsWith('.') &&
          typeof options.baseUrl === 'string');
      return {
        resolved_path: toRelative(root, resolved),
        resolution_path: configResolved
          ? 'path_alias'
          : resolutionLabel(specifier, resolved, resolution.resolvedModule),
        reason: null,
      };
    }
  }

  const aliased = aliasMatched
    ? aliasFile(specifier, options, root, configPath)
    : null;
  if (aliased !== null) {
    return {
      resolved_path: toRelative(root, aliased),
      resolution_path: 'path_alias',
      reason: null,
    };
  }

  const workspace = findWorkspacePackage(specifier, workspaces);
  if (workspace !== null) {
    const entry = workspaceEntry(workspace, workspaces);
    if (entry.path === null) {
      return unresolved(entry.reason || 'workspace package entry not found');
    }
    if (!isInside(root, entry.path)) {
      return unresolved('workspace path outside the repository');
    }
    if (!isFile(entry.path)) {
      return unresolved('workspace package entry not found');
    }
    return {
      resolved_path: toRelative(root, entry.path),
      resolution_path: 'workspace_package',
      reason: null,
    };
  }

  if (resolution.resolvedModule === undefined) {
    if (aliasMatched) {
      if (aliasTouchesDependency(specifier, options, root, configPath)) {
        return unresolved('module not found');
      }
      return unresolved('path alias matches no configured path');
    }
    return unresolved('module not found');
  }

  return unresolved('module not found');
}

function resolveAsset(reference, root, maxFileBytes, configCache, configFiles, workspaces) {
  const source = path.resolve(root, ...reference.source.split('/'));
  const specifier = stripSuffix(reference.specifier);
  const configPath = nearestConfig(source, root);
  let options = {};
  if (configPath !== null) {
    configFiles.add(toRelative(root, configPath));
    const loaded = loadConfig(configPath, maxFileBytes, configCache, workspaces, root);
    if (loaded.error !== undefined) {
      return unresolved(loaded.error);
    }
    options = loaded.options;
  }

  // The compiler and its aliases come first. The exact path is only a fallback,
  // because the compiler does not normally resolve CSS, SVG or image files.
  const aliasMatched = configPath !== null && aliasMatches(specifier, options);
  const resolution = ts.resolveModuleName(
    specifier,
    source,
    options,
    resolutionHost(maxFileBytes),
  );
  if (resolution.resolvedModule !== undefined) {
    const resolved = path.normalize(resolution.resolvedModule.resolvedFileName);
    if (isInside(root, resolved)) {
      return {
        resolved_path: toRelative(root, resolved),
        resolution_path: aliasMatched
          ? 'path_alias'
          : resolutionLabel(specifier, resolved, resolution.resolvedModule),
        reason: null,
      };
    }
  }

  const aliased = aliasFile(specifier, options, root, configPath);
  if (aliased !== null) {
    return {
      resolved_path: toRelative(root, aliased),
      resolution_path: 'path_alias',
      reason: null,
    };
  }

  const candidate = path.resolve(path.dirname(source), specifier);
  if (!isInside(root, candidate) || !isFile(candidate)) {
    return unresolved('asset path matches no file');
  }
  return {
    resolved_path: toRelative(root, candidate),
    resolution_path: 'asset',
    reason: null,
  };
}

function unresolved(reason) {
  return { resolved_path: null, resolution_path: null, reason };
}

function nearestConfig(source, root) {
  let folder = path.dirname(source);
  while (true) {
    for (const name of CONFIG_NAMES) {
      const candidate = path.join(folder, name);
      if (isRealFile(candidate)) {
        return candidate;
      }
    }
    if (path.resolve(folder) === path.resolve(root)) {
      return null;
    }
    const parent = path.dirname(folder);
    if (parent === folder || !isInside(root, parent)) {
      return null;
    }
    folder = parent;
  }
}

function readWorkspaces(root, maxFileBytes) {
  const patterns = [];
  const rootManifest = readJsonFile(path.join(root, 'package.json'), maxFileBytes);
  if (rootManifest !== null) {
    addWorkspacePatterns(rootManifest.workspaces, patterns);
  }
  const pnpmFile = path.join(root, 'pnpm-workspace.yaml');
  if (isRealFile(pnpmFile)) {
    patterns.push(...readPnpmPatterns(pnpmFile, maxFileBytes));
  }

  const folders = new Set();
  const excluded = new Set();
  for (const pattern of patterns) {
    const trimmed = pattern.trim();
    const negative = trimmed.startsWith('!');
    const target = negative ? trimmed.slice(1) : trimmed;
    const found = expandWorkspacePattern(root, target);
    for (const folder of found) {
      if (negative) {
        excluded.add(folder);
      } else {
        folders.add(folder);
      }
    }
  }
  for (const folder of excluded) {
    folders.delete(folder);
  }

  const packages = new Map();
  for (const folder of folders) {
    const manifest = readJsonFile(path.join(folder, 'package.json'), maxFileBytes);
    if (manifest === null || typeof manifest.name !== 'string' || manifest.name.length === 0) {
      continue;
    }
    packages.set(manifest.name, { folder, manifest });
  }
  return packages;
}

function addWorkspacePatterns(value, patterns) {
  if (Array.isArray(value)) {
    for (const item of value) {
      if (typeof item === 'string') {
        patterns.push(item);
      }
    }
    return;
  }
  if (value !== null && typeof value === 'object' && Array.isArray(value.packages)) {
    for (const item of value.packages) {
      if (typeof item === 'string') {
        patterns.push(item);
      }
    }
  }
}

function readPnpmPatterns(file, maxFileBytes) {
  const text = safeRead(file, maxFileBytes);
  const patterns = [];
  let inPackages = false;
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (trimmed.startsWith('packages:')) {
      inPackages = true;
      continue;
    }
    if (!inPackages || trimmed.length === 0 || trimmed.startsWith('#')) {
      continue;
    }
    if (trimmed.startsWith('-')) {
      const value = trimmed
        .slice(1)
        .trim()
        .replace(/\s+#.*$/, '')
        .replace(/^['"]|['"]$/g, '');
      if (value.length > 0) {
        patterns.push(value);
      }
      continue;
    }
    break;
  }
  return patterns;
}

function expandWorkspacePattern(root, pattern) {
  const cleaned = pattern.trim().replace(/^\.\//, '');
  if (cleaned.length === 0) {
    return [];
  }
  return expandWorkspaceSegments(root, cleaned.split('/').filter((part) => part.length > 0));
}

function expandWorkspaceSegments(base, segments) {
  if (segments.length === 0) {
    return [base];
  }
  const [segment, ...rest] = segments;
  if (segment === '**') {
    const found = [...expandWorkspaceSegments(base, rest)];
    for (const name of readDirectoryNames(base)) {
      if (isIgnoredWorkspaceName(name)) {
        continue;
      }
      const child = path.join(base, name);
      if (isDirectory(child) && !isSymbolicLink(child)) {
        found.push(...expandWorkspaceSegments(child, segments));
      }
    }
    return found;
  }
  if (segment.includes('*') || segment.includes('?')) {
    const pattern = segmentPattern(segment);
    const found = [];
    for (const name of readDirectoryNames(base)) {
      if (isIgnoredWorkspaceName(name)) {
        continue;
      }
      const child = path.join(base, name);
      if (pattern.test(name) && isDirectory(child) && !isSymbolicLink(child)) {
        found.push(...expandWorkspaceSegments(child, rest));
      }
    }
    return found;
  }
  const child = path.join(base, segment);
  return isDirectory(child) ? expandWorkspaceSegments(child, rest) : [];
}

function segmentPattern(segment) {
  const escaped = segment.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^${escaped.replace(/\*/g, '[^/]*').replace(/\?/g, '.')}$`);
}

function isIgnoredWorkspaceName(name) {
  return name === 'node_modules' || name === '.git' || name === '.hg' || name === '.svn';
}

function readDirectoryNames(folder) {
  try {
    return fs.readdirSync(folder, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => entry.name);
  } catch {
    return [];
  }
}

function readJsonFile(file, maxFileBytes) {
  if (!isRealFile(file)) {
    return null;
  }
  try {
    const text = safeRead(file, maxFileBytes);
    const value = JSON.parse(text);
    return value !== null && typeof value === 'object' ? value : null;
  } catch {
    return null;
  }
}

function findWorkspacePackage(specifier, workspaces) {
  let best = null;
  for (const name of workspaces.keys()) {
    if (specifier === name || specifier.startsWith(name + '/')) {
      if (best === null || name.length > best.length) {
        best = name;
      }
    }
  }
  if (best === null) {
    return null;
  }
  return {
    name: best,
    subpath: specifier === best ? '' : specifier.slice(best.length + 1),
  };
}

function workspaceEntry(match, workspaces) {
  const pkg = workspaces.get(match.name);
  if (pkg === undefined) {
    return { path: null, reason: 'workspace package entry not found' };
  }
  if (match.subpath.split('/').includes('..')) {
    return { path: null, reason: 'workspace path outside the repository' };
  }
  let target = null;
  if (match.subpath.length > 0) {
    target = exportTarget(pkg.manifest.exports, `./${match.subpath}`, match.subpath);
    if (target === null) {
      if (pkg.manifest.exports !== undefined) {
        return {
          path: null,
          reason: 'workspace package subpath is not exported',
        };
      }
      target = match.subpath;
    }
  } else {
    target = exportTarget(pkg.manifest.exports, '.', '');
    if (target === null) {
      target = firstString(
        pkg.manifest.types,
        pkg.manifest.typings,
        pkg.manifest.main,
        pkg.manifest.module,
      );
    }
  }
  if (typeof target !== 'string') {
    return { path: null, reason: 'workspace package entry not found' };
  }
  const resolved = resolveFileCandidate(path.resolve(pkg.folder, target));
  if (resolved === null) {
    return { path: null, reason: 'workspace package entry not found' };
  }
  return { path: resolved, reason: null };
}

function exportTarget(value, key, wildcardValue) {
  if (typeof value === 'string') {
    return key === '.' ? value : null;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const target = exportTarget(item, key, wildcardValue);
      if (target !== null) {
        return target;
      }
    }
    return null;
  }
  if (value === null || typeof value !== 'object') {
    return null;
  }
  if (Object.prototype.hasOwnProperty.call(value, key)) {
    return conditionTarget(value[key]);
  }
  for (const pattern of Object.keys(value)) {
    if (!pattern.includes('*')) {
      continue;
    }
    const star = pattern.indexOf('*');
    const prefix = pattern.slice(0, star);
    const suffix = pattern.slice(star + 1);
    if (!key.startsWith(prefix) || !key.endsWith(suffix)) {
      continue;
    }
    const captured = key.slice(prefix.length, key.length - suffix.length);
    const target = conditionTarget(value[pattern]);
    if (typeof target === 'string') {
      return target.replace(/\*/g, captured);
    }
  }
  if (key === '.') {
    return conditionTarget(value);
  }
  return null;
}

function conditionTarget(value) {
  if (typeof value === 'string') {
    return value;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const target = conditionTarget(item);
      if (target !== null) {
        return target;
      }
    }
    return null;
  }
  if (value === null || typeof value !== 'object') {
    return null;
  }
  for (const key of ['types', 'typings', 'import', 'require', 'node', 'default']) {
    if (Object.prototype.hasOwnProperty.call(value, key)) {
      const target = conditionTarget(value[key]);
      if (target !== null) {
        return target;
      }
    }
  }
  for (const item of Object.values(value)) {
    const target = conditionTarget(item);
    if (target !== null) {
      return target;
    }
  }
  return null;
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === 'string' && value.length > 0) {
      return value;
    }
  }
  return null;
}

function resolveFileCandidate(candidate) {
  if (isFile(candidate)) {
    return candidate;
  }
  const known = ['.ts', '.tsx', '.js', '.jsx', '.d.ts', '.json'];
  for (const extension of known) {
    if (isFile(candidate + extension)) {
      return candidate + extension;
    }
  }
  const indexNames = ['index.ts', 'index.tsx', 'index.js', 'index.jsx', 'index.d.ts'];
  for (const name of indexNames) {
    const index = path.join(candidate, name);
    if (isFile(index)) {
      return index;
    }
  }
  return null;
}

function rewriteExtends(config, workspaces, root) {
  const value = config.extends;
  if (typeof value === 'string') {
    const target = workspaceConfigPath(value, workspaces, root);
    if (target !== null) {
      config.extends = target;
    }
    return;
  }
  if (Array.isArray(value)) {
    config.extends = value.map((item) => {
      if (typeof item !== 'string') {
        return item;
      }
      const target = workspaceConfigPath(item, workspaces, root);
      return target === null ? item : target;
    });
  }
}

function workspaceConfigPath(specifier, workspaces, root) {
  const match = findWorkspacePackage(specifier, workspaces);
  if (match === null) {
    return null;
  }
  const pkg = workspaces.get(match.name);
  if (pkg === undefined) {
    throw new ConfigError('workspace configuration file not found');
  }
  if (match.subpath.split('/').includes('..')) {
    throw new ConfigError('workspace path outside the repository');
  }
  const candidate = match.subpath.length > 0
    ? path.resolve(pkg.folder, match.subpath)
    : path.join(pkg.folder, 'tsconfig.json');
  if (!isInside(root, candidate)) {
    throw new ConfigError('workspace path outside the repository');
  }
  const resolved = resolveFileCandidate(candidate);
  if (resolved === null) {
    throw new ConfigError('workspace configuration file not found');
  }
  if (!isInside(root, resolved)) {
    throw new ConfigError('workspace path outside the repository');
  }
  return resolved;
}

function isSymbolicLink(value) {
  try {
    return fs.lstatSync(value).isSymbolicLink();
  } catch {
    return true;
  }
}

function isLink(value) {
  try {
    return fs.lstatSync(value).isSymbolicLink();
  } catch {
    return false;
  }
}

function loadConfig(configPath, maxFileBytes, cache, workspaces, root) {
  const cached = cache.get(configPath);
  if (cached !== undefined) {
    return cached;
  }
  let outcome;
  try {
    if (isLink(configPath)) {
      throw new ConfigError('symbolic link');
    }
    ensureWithinSize(configPath, maxFileBytes);
    const config = readConfigObject(configPath, maxFileBytes, workspaces, root);
    const parsed = ts.parseJsonConfigFileContent(
      config,
      parseHost(maxFileBytes, workspaces, root),
      path.dirname(configPath),
      undefined,
      configPath,
    );
    if (parsed.errors.length > 0) {
      throw new ConfigError('configuration file has invalid syntax');
    }
    outcome = { options: parsed.options };
  } catch (error) {
    if (error instanceof ConfigError) {
      outcome = { error: error.message };
    } else {
      outcome = { error: 'configuration file cannot be read' };
    }
  }
  cache.set(configPath, outcome);
  return outcome;
}

function readConfigObject(configPath, maxFileBytes, workspaces, root) {
  if (isLink(configPath)) {
    throw new ConfigError('symbolic link');
  }
  const text = safeRead(configPath, maxFileBytes);
  const parsed = ts.parseConfigFileTextToJson(configPath, text);
  if (parsed.error !== undefined || parsed.config === null || typeof parsed.config !== 'object') {
    throw new ConfigError('configuration file has invalid syntax');
  }
  const config = parsed.config;
  rewriteExtends(config, workspaces, root);
  return config;
}

function parseHost(maxFileBytes, workspaces, root) {
  return {
    useCaseSensitiveFileNames: ts.sys.useCaseSensitiveFileNames,
    fileExists: ts.sys.fileExists,
    readDirectory: ts.sys.readDirectory,
    readFile: (file) => readConfigFile(file, maxFileBytes, workspaces, root),
  };
}

function readConfigFile(file, maxFileBytes, workspaces, root) {
  if (isLink(file)) {
    throw new ConfigError('symbolic link');
  }
  const text = safeRead(file, maxFileBytes);
  if (!file.toLowerCase().endsWith('.json')) {
    return text;
  }
  const parsed = ts.parseConfigFileTextToJson(file, text);
  if (
    parsed.error !== undefined ||
    parsed.config === null ||
    typeof parsed.config !== 'object' ||
    (!('extends' in parsed.config) && !('compilerOptions' in parsed.config))
  ) {
    return text;
  }
  const config = parsed.config;
  rewriteExtends(config, workspaces);
  return JSON.stringify(config);
}

function resolutionHost(maxFileBytes) {
  return {
    fileExists: ts.sys.fileExists,
    readFile: (file) => safeRead(file, maxFileBytes),
    directoryExists: ts.sys.directoryExists,
    getCurrentDirectory: () => process.cwd(),
    getDirectories: ts.sys.getDirectories,
    realpath: ts.sys.realpath,
  };
}

function safeRead(file, maxFileBytes) {
  ensureWithinSize(file, maxFileBytes);
  return fs.readFileSync(file, 'utf8');
}

function ensureWithinSize(file, maxFileBytes) {
  let stat;
  try {
    stat = fs.statSync(file);
  } catch {
    throw new ConfigError('configuration file cannot be read');
  }
  if (stat.size > maxFileBytes) {
    throw new ConfigError('configuration file exceeds size limit');
  }
}

function aliasMatches(specifier, options) {
  const paths = options && options.paths;
  if (!paths || typeof paths !== 'object') {
    return false;
  }
  return Object.keys(paths).some((pattern) => {
    const star = pattern.indexOf('*');
    if (star === -1) {
      return specifier === pattern;
    }
    const prefix = pattern.slice(0, star);
    const suffix = pattern.slice(star + 1);
    return (
      specifier.length >= prefix.length + suffix.length &&
      specifier.startsWith(prefix) &&
      specifier.endsWith(suffix)
    );
  });
}

function aliasFile(specifier, options, root, configPath) {
  for (const candidate of aliasTargets(specifier, options, root, configPath)) {
    const resolved = resolveFileCandidate(candidate);
    if (resolved !== null && isInside(root, resolved) && isFile(resolved)) {
      return resolved;
    }
  }
  return null;
}

function aliasTouchesDependency(specifier, options, root, configPath) {
  return aliasTargets(specifier, options, root, configPath).some((candidate) =>
    candidate.split(/[\\/]/).includes('node_modules'),
  );
}

function aliasTargets(specifier, options, root, configPath) {
  const paths = options && options.paths;
  if (!paths || typeof paths !== 'object') {
    return [];
  }
  const base = typeof options.baseUrl === 'string'
    ? options.baseUrl
    : configPath === null
      ? root
      : path.dirname(configPath);
  const targets = [];
  for (const pattern of Object.keys(paths)) {
    const star = pattern.indexOf('*');
    let captured = '';
    if (star === -1) {
      if (specifier !== pattern) {
        continue;
      }
    } else {
      const prefix = pattern.slice(0, star);
      const suffix = pattern.slice(star + 1);
      if (
        specifier.length < prefix.length + suffix.length ||
        !specifier.startsWith(prefix) ||
        !specifier.endsWith(suffix)
      ) {
        continue;
      }
      captured = specifier.slice(prefix.length, specifier.length - suffix.length);
    }
    const values = Array.isArray(paths[pattern]) ? paths[pattern] : [paths[pattern]];
    for (const target of values) {
      if (typeof target !== 'string') {
        continue;
      }
      targets.push(path.resolve(base, target.replace(/\*/g, captured)));
    }
  }
  return targets;
}

function stripSuffix(specifier) {
  return specifier.split('?')[0].split('#')[0];
}

function resolutionLabel(specifier, resolved, resolvedModule) {
  if (
    resolvedModule.packageId !== undefined ||
    resolved.split(/[\\/]/).includes('node_modules')
  ) {
    return 'package_entry_point';
  }
  const resolvedBase = path.basename(resolved);
  const specifierBase = specifier.split('/').pop() || specifier;
  if (specifierBase === resolvedBase) {
    return 'relative';
  }
  const stem = resolvedBase.replace(/\.(d\.ts|ts|tsx|js|jsx)$/, '');
  const specifierStem = specifierBase.replace(/\.(d\.ts|ts|tsx|js|jsx)$/, '');
  if (stem === 'index' && specifierStem !== 'index') {
    return 'index_file';
  }
  return 'extension';
}

function isRepositoryRelative(value) {
  if (path.isAbsolute(value)) {
    return false;
  }
  return value
    .split('/')
    .every((part) => part !== '' && part !== '.' && part !== '..');
}

function isInside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative === '' || (relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative));
}

function isDependencyPath(value) {
  return value.split(/[\\/]/).includes('node_modules');
}

function isDirectory(value) {
  try {
    return fs.statSync(value).isDirectory();
  } catch {
    return false;
  }
}

function isFile(value) {
  try {
    return fs.statSync(value).isFile();
  } catch {
    return false;
  }
}

function isRealFile(value) {
  try {
    const stat = fs.lstatSync(value);
    return stat.isFile() && !stat.isSymbolicLink();
  } catch {
    return false;
  }
}

function toRelative(root, candidate) {
  return path.relative(root, candidate).split(path.sep).join('/');
}

function refuse(code, message, status) {
  write({ protocol_version: PROTOCOL_VERSION, error: { code, message } });
  process.exitCode = status;
}

function write(value) {
  fs.writeSync(1, `${JSON.stringify(value)}\n`);
}

main();
