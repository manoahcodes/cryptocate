from django.http import JsonResponse
from django.shortcuts import redirect

def health_check(request):
    return JsonResponse({ "status": "ok" })

def telegram_redirect_view(request):
    return redirect("https://t.me/cryptocatebot")