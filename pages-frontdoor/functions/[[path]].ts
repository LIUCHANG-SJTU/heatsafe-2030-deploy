interface Env {
  HEATSAFE: Fetcher;
}

export const onRequest: PagesFunction<Env> = async (context) =>
  context.env.HEATSAFE.fetch(context.request);
