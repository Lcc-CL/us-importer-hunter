// Only these exact operations bypass the shared operator access passcode.
export function isPublicMailRoute(path: string, method: string): boolean {
  if (path === "/api/v1/mail-feedback") return method === "POST";
  return (
    (method === "GET" || method === "POST") &&
    /^\/api\/v1\/mail-unsubscribe\/[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(path)
  );
}
