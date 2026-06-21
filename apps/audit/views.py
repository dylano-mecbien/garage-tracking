from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import AuditLog

@login_required
def audit_logs(request):
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:500]
    return render(request, 'admin_custom/audit_logs.html', {'logs': logs})
