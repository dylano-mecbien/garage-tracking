from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Reception

class ReceptionSerializer(serializers.ModelSerializer):
    vehicule_immat = serializers.CharField(source='vehicule.immatriculation', read_only=True)
    class Meta:
        model = Reception
        fields = '__all__'



class ReceptionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Reception.objects.select_related('vehicule').order_by('-created_at')
    serializer_class = ReceptionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['statut']
    search_fields = ['vehicule__immatriculation', 'numero']





router = DefaultRouter()
router.register('receptions', ReceptionViewSet)
urlpatterns = router.urls
