from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.db.models import F
from django.views.decorators.http import require_POST
from django.contrib import messages

from .models import LinkMapping, ClickLog
from datetime import timedelta
from . import service

import qrcode
import base64
from io import BytesIO
import socket


# Helper function: get client IP
def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


# 📊 Stats Page
def stats(request, url_hash):
    lm = get_object_or_404(LinkMapping, hash=url_hash)
    logs = lm.clicks.order_by('-clicked_at')[:25]  # last 25 clicks

    # Detect local IP automatically
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    # Build shortened URL with local IP instead of 127.0.0.1
    shortened_url = f"http://{local_ip}:8000{reverse('redirect', args=[lm.hash])}"

    # ✅ Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(shortened_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    qr_img = base64.b64encode(buffer.getvalue()).decode()

    return render(request, 'main/stats.html', {
        'link': lm,
        'logs': logs,
        'shortened_url': shortened_url,
        'qr_img': qr_img,
    })


# 🏠 Home Page
def index(request):
    return render(request, 'main/index.html')


# ✂️ Shorten URL
def shorten(request, url):
    custom_hash = request.POST.get('custom_hash', None)
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url

    try:
        shortened_url_hash = service.shorten(url, custom_hash)

        # Handle expiry days (optional)
        expire_days = request.POST.get('expire_days')
        expires_at = None
        if expire_days:
            try:
                expires_at = timezone.now() + timedelta(days=int(expire_days))
            except ValueError:
                expires_at = None

        # Save mapping info (activate + expiry)
        lm, _ = LinkMapping.objects.get_or_create(
            hash=shortened_url_hash,
            defaults={'original_url': url}
        )
        if expires_at:
            lm.expires_at = expires_at
        lm.is_active = True
        lm.save()

        # Detect local IP automatically
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        shortened_url = f"http://{local_ip}:8000{reverse('redirect', args=[shortened_url_hash])}"

        # ✅ Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(shortened_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        qr_img = base64.b64encode(buffer.getvalue()).decode()

        lm.refresh_from_db()  # ensure latest data
        context = {
            'shortened_url': shortened_url,
            'original_url': url,
            'hash': shortened_url_hash,
            'qr_img': qr_img,
            'click_count': lm.click_count,
        }

        messages.success(request, "🎉 Your link has been shortened successfully!")
        return render(request, 'main/link.html', context)

    except ValidationError as e:
        messages.error(request, f"❌ {e.messages[0]}")
        return render(request, 'main/index.html', {
            'url': url,
            'custom_hash': custom_hash
        })


def shorten_post(request):
    return shorten(request, request.POST['url'])


# 🔗 Redirect handler
def redirect_hash(request, url_hash):
    lm = get_object_or_404(LinkMapping, hash=url_hash)

    # Block if deactivated or expired
    if not lm.is_active or lm.is_expired:
        return render(request, 'main/deactivated.html', {'link': lm}, status=410)

    # Log click
    ClickLog.objects.create(
        link=lm,
        ip=_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        referrer=request.META.get('HTTP_REFERER', '')
    )

    # Increment click counter
    LinkMapping.objects.filter(pk=lm.pk).update(click_count=F('click_count') + 1)

    return redirect(lm.original_url)


# 🚫 Deactivate Link
@require_POST
def deactivate_link(request, url_hash):
    link = get_object_or_404(LinkMapping, hash=url_hash)
    link.is_active = False
    link.save()
    messages.warning(request, "⚠️ Link has been deactivated.")
    return redirect('stats', url_hash=url_hash)


# ✅ Activate Link
@require_POST
def activate_link(request, url_hash):
    link = get_object_or_404(LinkMapping, hash=url_hash)
    link.is_active = True
    link.save()
    messages.success(request, "✅ Link has been activated successfully!")
    return redirect('stats', url_hash=url_hash)
