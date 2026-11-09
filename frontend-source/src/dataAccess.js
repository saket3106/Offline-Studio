// Single native boundary. Backend names, arguments, signals and callbacks stay unchanged.
const adapters = new WeakMap();
export function createDesktopAdapter(native) {
  if (!native) return null;
  if (adapters.has(native)) return adapters.get(native);
  const methods = new Map();
  const adapter = new Proxy(native, {
    get(target, key) {
      const member = Reflect.get(target, key);
      if (typeof member !== "function") return member;
      if (!methods.has(key))
        methods.set(key, (...args) => member.apply(target, args));
      return methods.get(key);
    },
  });
  adapters.set(native, adapter);
  return adapter;
}
export function desktopCall(bridge, method, ...args) {
  return new Promise((resolve, reject) => {
    if (!bridge?.[method]) return resolve(null);
    try {
      bridge[method](...args, resolve);
    } catch (error) {
      reject(error);
    }
  });
}
