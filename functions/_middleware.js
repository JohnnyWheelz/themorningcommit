export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (url.hostname.toLowerCase() === "www.themorningcommit.com") {
    url.hostname = "themorningcommit.com";
    url.protocol = "https:";
    return Response.redirect(url.toString(), 301);
  }
  return context.next();
}
