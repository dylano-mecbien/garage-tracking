from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from .models import OrdreReparation, Tache, Atelier

class AtelierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Atelier
        fields = '__all__'

class ORSerializer(serializers.ModelSerializer):
    vehicule_immat = serializers.CharField(source='vehicule.immatriculation', read_only=True)
    class Meta:
        model = OrdreReparation
        fields = '__all__'

class TacheSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tache
        fields = '__all__'

class AtelierViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Atelier.objects.filter(is_active=True)
    serializer_class = AtelierSerializer
    permission_classes = [IsAuthenticated]

class ORViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrdreReparation.objects.select_related('vehicule', 'atelier').order_by('-date_creation')
    serializer_class = ORSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['statut', 'type_or', 'atelier']
    search_fields = ['numero', 'vehicule__immatriculation']

class TacheViewSet(viewsets.ModelViewSet):
    queryset = Tache.objects.select_related('ordre_reparation', 'technicien').order_by('-created_at')
    serializer_class = TacheSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['statut', 'priorite', 'technicien']

router = DefaultRouter()
router.register('ateliers', AtelierViewSet)
router.register('ordres-reparation', ORViewSet)
router.register('taches', TacheViewSet)
urlpatterns = router.urls
