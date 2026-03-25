import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Protect /signals — redirect to sign-in if not authenticated
const isProtectedRoute = createRouteMatcher(["/signals"]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtectedRoute(req)) {
    const authObj = await auth();
    if (!authObj.userId) {
      authObj.redirectToSignIn();
    }
  }
});

export const config = {
  matcher: ["/((?!.*\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};