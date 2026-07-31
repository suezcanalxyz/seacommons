#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SeaCommonsRaft.generated.h"

class UBuoyancyComponent;
class UStaticMeshComponent;

/**
 * Anonymous research raft with a physics hull and four calibrated pontoons.
 *
 * It intentionally carries no vessel identity. The parameters are a visual
 * baseline and must be replaced when a validated vessel model is available.
 */
UCLASS(Blueprintable)
class SEACOMMONSIMMERSIVE_API ASeaCommonsRaft : public AActor
{
    GENERATED_BODY()

public:
    ASeaCommonsRaft();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "SeaCommons|Vessel")
    TObjectPtr<UStaticMeshComponent> Hull;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "SeaCommons|Vessel")
    TObjectPtr<UStaticMeshComponent> Cabin;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "SeaCommons|Vessel")
    TObjectPtr<UBuoyancyComponent> Buoyancy;

protected:
    virtual void BeginPlay() override;
};
