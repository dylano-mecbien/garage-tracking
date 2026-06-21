from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from .models import EnregistrementEntree, BonSortie

class EntreeSerializer(serializers.ModelSerializer):
    vehicule_immat = serializers.CharField(source='vehicule.immatriculation', read_only=True)
    class Meta:
        model = EnregistrementEntree
        fields = '__all__'

class BonSortieSerializer(serializers.ModelSerializer):
    class Meta:
        model = BonSortie
        fields = '__all__'

class EntreeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EnregistrementEntree.objects.select_related('vehicule').order_by('-date_entree')
    serializer_class = EntreeSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['statut', 'motif']
    search_fields = ['vehicule__immatriculation', 'numero']

class BonSortieViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BonSortie.objects.select_related('vehicule').order_by('-created_at')
    serializer_class = BonSortieSerializer
    permission_classes = [IsAuthenticated]

router = DefaultRouter()
router.register('entrees', EntreeViewSet)
router.register('bons-sortie', BonSortieViewSet)
urlpatterns = router.urls
